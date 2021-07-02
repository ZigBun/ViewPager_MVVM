
# Generated by Django 2.1.2 on 2018-10-17 19:42
import os

from django.db import migrations
from prices import Money

from .. import ChargeStatus, TransactionKind


class PaymentStatus:
    WAITING = "waiting"
    PREAUTH = "preauth"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    ERROR = "error"
    INPUT = "input"


def is_fully_refunded(payment):
    total = Money(payment.total, payment.currency)
    return total == payment.order.total_gross


def get_charge_amount(payment):
    return payment.total - payment.captured_amount


def get_charge_status(payment):
    if payment.status == PaymentStatus.CONFIRMED:
        if get_charge_amount(payment) <= 0:
            return ChargeStatus.FULLY_CHARGED
        return ChargeStatus.PARTIALLY_CHARGED
    if payment.status == PaymentStatus.REFUNDED:
        if is_fully_refunded(payment):
            return ChargeStatus.FULLY_REFUNDED
        return ChargeStatus.PARTIALLY_REFUNDED
    return ChargeStatus.NOT_CHARGED


def get_is_active(status, payment):
    if status == PaymentStatus.INPUT:
        return False
    if status == PaymentStatus.REFUNDED and is_fully_refunded(payment):
        return False
    return True


def create_transaction(method, kind, created, amount, is_success, currency, token):
    return method.transactions.create(
        created=created,
        kind=kind,
        is_success=is_success,
        amount=amount,
        token=token,
        currency=currency,
        gateway_response={},
    )


def create_transactions(method, payment):
    # Those payments are inactive and need no transactions
    if payment.status == PaymentStatus.INPUT:
        return

    # Other payments needed to be authorized first
    created = payment.created_at
    create_transaction(
        method=method,
        kind=TransactionKind.AUTH,
        created=created,
        amount=payment.total,
        currency=payment.currency,
        is_success=True,
        token=payment.transaction_id,
    )
    # This kind of payment needs an unsuccessful capture transaction
    if payment.status in [PaymentStatus.ERROR, PaymentStatus.REJECTED]:
        create_transaction(
            method=method,
            kind=TransactionKind.CAPTURE,
            created=created,
            amount=payment.total,
            currency=payment.currency,
            is_success=False,
            token=payment.transaction_id,
        )
        return

    # Two other payments left - CONFIRMED and REFUNDED needs to be captured
    create_transaction(
        method=method,
        kind=TransactionKind.CAPTURE,
        created=created,
        amount=payment.total,
        currency=payment.currency,
        is_success=True,
        token=payment.transaction_id,
    )

    # If payment was refunded, we need to create a refund transaction for it
    if payment.status == PaymentStatus.REFUNDED:
        create_transaction(
            method=method,
            kind=TransactionKind.REFUND,
            created=created,
            amount=payment.total,
            currency=payment.currency,
            is_success=True,
            token=payment.transaction_id,
        )


def transfer_payments_to_payment_methods(apps, schema_editor):
    PaymentMethod = apps.get_model("payment", "PaymentMethod")
    Payment = apps.get_model("order", "Payment")
    payments = Payment.objects.all()

    for pay in payments:
        extra_data = {
            "fraud_status": pay.fraud_status,
            "fraud_message": pay.fraud_message,
            "transaction_id": pay.transaction_id,
            "delivery_fee": pay.delivery,
            "message": pay.message,
            "description": pay.description,
            "extra_data": pay.extra_data,
            "tax": pay.tax,
        }
        payment_method = PaymentMethod.objects.create(
            order=pay.order,
            gateway=pay.variant,
            created=pay.created_at,
            modified=pay.modified,
            billing_first_name=pay.billing_first_name,
            billing_last_name=pay.billing_last_name,
            billing_address_1=pay.billing_address_1,
            billing_address_2=pay.billing_address_2,
            billing_city=pay.billing_city,
            billing_country_code=pay.billing_country_code,
            billing_country_area=pay.billing_country_area,
            billing_email=pay.billing_email,
            customer_ip_address=pay.customer_ip_address,
            extra_data=extra_data,
            token=pay.token,
            captured_amount=pay.captured_amount,
            total=pay.total,
            currency=pay.currency or os.environ.get("DEFAULT_CURRENCY", "USD"),
            is_active=get_is_active(pay.status, pay),
            charge_status=get_charge_status(pay),
        )
        create_transactions(payment_method, pay)


class Migration(migrations.Migration):
    dependencies = [("payment", "0001_initial")]

    operations = [
        migrations.RunPython(
            transfer_payments_to_payment_methods, migrations.RunPython.noop
        )
    ]