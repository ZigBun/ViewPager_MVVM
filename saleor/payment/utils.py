import json
import logging
from decimal import Decimal
from typing import Dict, List, Optional, cast, overload

import graphene
from babel.numbers import get_currency_precision
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q

from ..account.models import User
from ..checkout.fetch import fetch_checkout_info, fetch_checkout_lines
from ..checkout.models import Checkout
from ..core.prices import quantize_price
from ..core.tracing import traced_atomic_transaction
from ..discount.utils import fetch_active_discounts
from ..order.models import Order
from ..order.utils import update_order_authorize_data, update_order_charge_data
from ..plugins.manager import PluginsManager, get_plugins_manager
from . import (
    ChargeStatus,
    GatewayError,
    PaymentError,
    StorePaymentMethod,
    TransactionKind,
)
from .error_codes import PaymentErrorCode
from .interface import (
    AddressData,
    GatewayResponse,
    PaymentData,
    PaymentLineData,
    PaymentLinesData,
    PaymentMethodInfo,
    RefundData,
    StorePaymentMethodEnum,
    TransactionData,
)
from .models import Payment, Transaction

logger = logging.getLogger(__name__)

GENERIC_TRANSACTION_ERROR = "Transaction was unsuccessful"
ALLOWED_GATEWAY_KINDS = {choices[0] for choices in TransactionKind.CHOICES}


def create_payment_lines_information(
    payment: Payment,
    manager: PluginsManager,
) -> PaymentLinesData:
    checkout = payment.checkout
    order = payment.order

    if checkout:
        return create_checkout_payment_lines_information(checkout, manager)
    elif order:
        return create_order_payment_lines_information(order)

    return PaymentLinesData(
        shipping_amount=Decimal("0.00"),
        voucher_amount=Decimal("0.00"),
        lines=[],
    )


def create_checkout_payment_lines_information(
    checkout: Checkout, manager: PluginsManager
) -> PaymentLinesData:
    line_items = []
    lines, _ = fetch_checkout_lines(checkout)
    discounts = fetch_active_discounts()
    checkout_info = fetch_checkout_info(checkout, lines, discounts, manager)
    address = checkout_info.shipping_address or checkout_info.billing_address

    for line_info in lines:
        unit_price = manager.calculate_checkout_line_unit_price(
            checkout_info,
            lines,
            line_info,
            address,
            discounts,
        )
        unit_gross = unit_price.gross.amount

        quantity = line_info.line.quantity
        product_name = f"{line_info.variant.product.name}, {line_info.variant.name}"
        product_sku = line_info.variant.sku
        line_items.append(
            PaymentLineData(
                quantity=quantity,
                product_name=product_name,
                product_sku=product_sku,
                variant_id=line_info.variant.id,
                amount=unit_gross,
            )
        )
    shipping_amount = manager.calculate_checkout_shipping(
        checkout_info=checkout_info,
        lines=lines,
        address=address,
        discounts=discounts,
    ).gross.amount

    voucher_amount = -checkout.discount_amount

    return PaymentLinesData(
        shipping_amount=shipping_amount,
        voucher_amount=voucher_amount,
        lines=line_items,
    )


def create_order_payment_lines_information(order: Order) -> PaymentLinesData:
    line_items = []
    for order_line in order.lines.all():
        product_name = f"{order_line.product_name}, {order_line.variant_name}"

        variant_id = order_line.variant_id
        if variant_id is None:
            continue

        line_items.append(
            PaymentLineData(
                quantity=order_line.quantity,
                product_name=product_name,
                product_sku=order_line.product_sku,
                variant_id=variant_id,
                amount=order_line.unit_price_gross_amount,
            )
        )

    shipping_amount = order.shipping_price_gross_amount
    voucher_amount = order.total_gross_amount - order.undiscounted_total_gross_amount

    return PaymentLinesData(
        shipping_amount=shipping_amount,
        voucher_amount=voucher_amount,
        lines=line_items,
    )


def generate_transactions_data(payment: Payment) -> List[TransactionData]:
    return [
        TransactionData(
            token=t.token,
            is_success=t.is_success,
            kind=t.kind,
            gateway_response=t.gateway_response,
            amount={
                "amount": str(quantize_price(t.amount, t.currency)),
                "currency": t.currency,
            },
        )
        for t in payment.transactions.all()
    ]


def create_payment_information(
    payment: Payment,
    payment_token: Optional[str] = None,
    amount: Optional[Decimal] = None,
    customer_id: Optional[str] = None,
    store_source: bool = False,
    refund_data: Optional[RefundData] = None,
    additional_data: Optional[dict] = None,
    manager: Optional[PluginsManager] = None,
) -> PaymentData:
    """Extract order information along with payment details.

    Returns information required to process payment and additional
    billing/shipping addresses for optional fraud-prevention mechanisms.
    """
    if checkout := payment.checkout:
        billing = checkout.billing_address
        shipping = checkout.shipping_address
        email = cast(str, checkout.get_customer_email())
        user_id = checkout.user_id
        checkout_token = str(checkout.token)
        from ..checkout.utils import get_or_create_checkout_metadata

        checkout_metadata = get_or_create_checkout_metadata(checkout).metadata
    elif order := payment.order:
        billing = order.billing_address
        shipping = order.shipping_address
        email = order.user_email
        user_id = order.user_id
        checkout_token = order.checkout_token
        checkout_metadata = None
    else:
        billing = None
        shipping = None
        email = payment.billing_email
        user_id = None
        checkout_token = ""
        checkout_metadata = None

    billing_address = AddressData(**billing.as_data()) if billing else None
    shipping_address = AddressData(**shipping.as_data()) if shipping else None

    order = payment.order
    order_id = order.pk if order else None
    channel_slug = order.channel.slug if order and order.channel else None
    graphql_payment_id = graphene.Node.to_global_id("Payment", payment.pk)

    graphql_customer_id = None
    if user_id:
        graphql_customer_id = graphene.Node.to_global_id("User", user_id)

    return PaymentData(
        gateway=payment.gateway,
        token=payment_token,
        amount=amount or payment.total,
        currency=payment.currency,
        billing=billing_address,
        shipping=shipping_address,
        order_id=str(order_id),
        order_channel_slug=channel_slug,
        payment_id=payment.pk,
        graphql_payment_id=graphql_payment_id,
        customer_ip_address=payment.customer_ip_address,
        customer_id=customer_id,
        customer_email=email,
        reuse_source=store_source,
        data=additional_data or {},
        graphql_customer_id=graphql_customer_id,
        store_payment_method=StorePaymentMethodEnum[
            payment.store_payment_method.upper()
        ],
        checkout_token=checkout_token,
        checkout_metadata=checkout_metadata,
        payment_metadata=payment.metadata,
        psp_reference=payment.psp_reference,
        refund_data=refund_data,
        transactions=generate_transactions_data(payment),
        _resolve_lines_data=lambda: create_payment_lines_information(
            payment, manager or get_plugins_manager()
        ),
    )


def create_payment(
    gateway: str,
    total: Decimal,
    currency: str,
    email: st