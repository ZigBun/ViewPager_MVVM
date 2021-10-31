from ..permission.enums import (
    AccountPermissions,
    AppPermission,
    ChannelPermissions,
    CheckoutPermissions,
    DiscountPermissions,
    GiftcardPermissions,
    MenuPermissions,
    OrderPermissions,
    PagePermissions,
    PageTypePermissions,
    PaymentPermissions,
    ProductPermissions,
    ShippingPermissions,
    SitePermissions,
)


class WebhookEventAsyncType:
    ANY = "any_events"

    ADDRESS_CREATED = "address_created"
    ADDRESS_UPDATED = "address_updated"
    ADDRESS_DELETED = "address_deleted"

    APP_INSTALLED = "app_installed"
    APP_UPDATED = "app_updated"
    APP_DELETED = "app_deleted"
    APP_STATUS_CHANGED = "app_status_changed"

    ATTRIBUTE_CREATED = "attribute_created"
    ATTRIBUTE_UPDATED = "attribute_updated"
    ATTRIBUTE_DELETED = "attribute_deleted"

    ATTRIBUTE_VALUE_CREATED = "attribute_value_created"
    ATTRIBUTE_VALUE_UPDATED = "attribute_value_updated"
    ATTRIBUTE_VALUE_DELETED = "attribute_value_deleted"

    CATEGORY_CREATED = "category_created"
    CATEGORY_UPDATED = "category_updated"
    CATEGORY_DELETED = "category_deleted"

    CHANNEL_CREATED = "channel_created"
    CHANNEL_UPDATED = "channel_updated"
    CHANNEL_DELETED = "channel_deleted"
    CHANNEL_STATUS_CHANGED = "channel_status_changed"

    GIFT_CARD_CREATED = "gift_card_created"
    GIFT_CARD_UPDATED = "gift_card_updated"
    GIFT_CARD_DELETED = "gift_card_deleted"
    GIFT_CARD_STATUS_CHANGED = "gift_card_status_changed"
    GIFT_CARD_METADATA_UPDATED = "gift_card_metadata_updated"

    MENU_CREATED = "menu_created"
    MENU_UPDATED = "menu_updated"
    MENU_DELETED = "menu_deleted"
    MENU_ITEM_CREATED = "menu_item_created"
    MENU_ITEM_UPDATED = "menu_item_updated"
    MENU_ITEM_DELETED = "menu_item_deleted"

    ORDER_CREATED = "order_created"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_FULLY_PAID = "order_fully_paid"
    ORDER_UPDATED = "order_updated"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_FULFILLED = "order_fulfilled"
    ORDER_METADATA_UPDATED = "order_metadata_updated"

    FULFILLMENT_CREATED = "fulfillment_created"
    FULFILLMENT_CANCELED = "fulfillment_canceled"
    FULFILLMENT_APPROVED = "fulfillment_approved"
    FULFILLMENT_METADATA_UPDATED = "fulfillment_metadata_updated"

    DRAFT_ORDER_CREATED = "draft_order_created"
    DRAFT_ORDER_UPDATED = "draft_order_updated"
    DRAFT_ORDER_DELETED = "draft_order_deleted"

    SALE_CREATED = "sale_created"
    SALE_UPDATED = "sale_updated"
    SALE_DELETED = "sale_deleted"
    SALE_TOGGLE = "sale_toggle"

    INVOICE_REQUESTED = "invoice_requested"
    INVOICE_DELETED = "invoice_deleted"
    INVOICE_SENT = "invoice_sent"

    CUSTOMER_CREATED = "customer_created"
    CUSTOMER_UPDATED = "customer_updated"
    CUSTOMER_DELETED = "customer_deleted"
    CUSTOMER_METADATA_UPDATED = "customer_metadata_updated"

    COLLECTION_CREATED = "collection_created"
    COLLECTION_UPDATED = "collection_updated"
    COLLECTION_DELETED = "collection_deleted"
    COLLECTION_METADATA_UPDATED = "collection_metadata_updated"

    PRODUCT_CREATED = "product_created"
    PRODUCT_UPDATED = "product_updated"
    PRODUCT_DELETED = "product_deleted"
    PRODUCT_METADATA_UPDATED = "product_metadata_updated"

    PRODUCT_MEDIA_CREATED = "product_media_created"
    PRODUCT_MEDIA_UPDATED = "product_media_updated"
    PRODUCT_MEDIA_DELETED = "product_media_deleted"

    PRODUCT_VARIANT_CREATED = "product_variant_created"
    PRODUCT_VARIANT_UPDATED = "product_variant_updated"
    PRODUCT_VARIANT_DELETED = "product_variant_deleted"
    PRODUCT_VARIANT_METADATA_UPDATED = "product_variant_metadata_updated"

    PRODUCT_VARIANT_OUT_OF_STOCK = "product_variant_out_of_stock"
    PRODUCT_VARIANT_BACK_IN_STOCK = "product_variant_back_in_stock"
    PRODUCT_VARIANT_STOCK_UPDATED = "product_variant_stock_updated"

    CHECKOUT_CREATED = "checkout_created"
    CHECKOUT_UPDATED = "checkout_updated"
    CHECKOUT_METADATA_UPDATED = "checkout_metadata_updated"

    NOTIFY_USER = "notify_user"

    PAGE_CREATED = "page_created"
    PAGE_UPDATED = "page_updated"
    PAGE_DELETED = "page_deleted"

    PAGE_TYPE_CREATED = "page_type_created"
    PAGE_TYPE_UPDATED = "page_type_updated"
    PAGE_TYPE_DELETED = "page_type_deleted"

    PERMISSION_GROUP_CREATED = "permission_group_created"
    PERMISSION_GROUP_UPDATED = "permission_group_updated"
    PERMISSION_GROUP_DELETED = "permission_group_deleted"

    SHIPPING_PRICE_CREATED = "shipping_price_created"
    SHIPPING_PRICE_UPDATED = "shipping_price_updated"
    SHIPPING_PRICE_DELETED = "shipping_price_deleted"

    SHIPPING_ZONE_CREATED = "shipping_zone_created"
    SHIPPING_ZONE_UPDATED = "shipping_zone_updated"
    SHIPPING_ZONE_DELETED = "shipping_zone_deleted"
    SHIPPING_ZONE_METADATA_UPDATED = "shipping_zone_metadata_updated"

    STAFF_CREATED = "staff_created"
    STAFF_UPDATED = "staff_updated"
    STAFF_DELETED = "staff_deleted"

    TRANSACTION_ACTION_REQUEST = "transaction_action_request"
    TRANSACTION_ITEM_METADATA_UPDATED = "transaction_item_metadata_updated"

    TRANSLATION_CREATED = "translation_created"
    TRANSLATION_UPDATED = "translation_updated"

    WAREHOUSE_CREATED = "warehouse_created"
    WAREHOUSE_UPDATED = "warehouse_updated"
    WAREHOUSE_DELETED = "warehouse_deleted"
    WAREHOUSE_METADATA_UPDATED = "warehouse_metadata_updated"

    VOUCHER_CREATED = "voucher_created"
    VOUCHER_UPDATED = "voucher_updated"
    VOUCHER_DELETED = "voucher_deleted"
    VOUCHER_METADATA_UPDATED = "voucher_metadata_updated"

    OBSERVABILITY = "observability"

    THUMBNAIL_CREATED = "thumbnail_created"

    DISPLAY_LABELS = {
        ANY: "Any events",
        