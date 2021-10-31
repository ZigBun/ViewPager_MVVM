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
        ADDRESS_CREATED: "Address created",
        ADDRESS_UPDATED: "Address updated",
        ADDRESS_DELETED: "Address deleted",
        APP_INSTALLED: "App created",
        APP_UPDATED: "App updated",
        APP_DELETED: "App deleted",
        APP_STATUS_CHANGED: "App status changed",
        ATTRIBUTE_CREATED: "Attribute created",
        ATTRIBUTE_UPDATED: "Attribute updated",
        ATTRIBUTE_DELETED: "Attribute deleted",
        ATTRIBUTE_VALUE_CREATED: "Attribute value created",
        ATTRIBUTE_VALUE_UPDATED: "Attribute value updated",
        ATTRIBUTE_VALUE_DELETED: "Attribute value deleted",
        CATEGORY_CREATED: "Category created",
        CATEGORY_UPDATED: "Category updated",
        CATEGORY_DELETED: "Category deleted",
        CHANNEL_CREATED: "Channel created",
        CHANNEL_UPDATED: "Channel updated",
        CHANNEL_DELETED: "Channel deleted",
        CHANNEL_STATUS_CHANGED: "Channel status changed",
        GIFT_CARD_CREATED: "Gift card created",
        GIFT_CARD_UPDATED: "Gift card updated",
        GIFT_CARD_DELETED: "Gift card deleted",
        GIFT_CARD_STATUS_CHANGED: "Gift card status changed",
        GIFT_CARD_METADATA_UPDATED: "Gift card metadata updated",
        MENU_CREATED: "Menu created",
        MENU_UPDATED: "Menu updated",
        MENU_DELETED: "Menu deleted",
        MENU_ITEM_CREATED: "Menu item created",
        MENU_ITEM_UPDATED: "Menu item updated",
        MENU_ITEM_DELETED: "Menu item deleted",
        ORDER_CREATED: "Order created",
        ORDER_CONFIRMED: "Order confirmed",
        ORDER_FULLY_PAID: "Order paid",
        ORDER_UPDATED: "Order updated",
        ORDER_CANCELLED: "Order cancelled",
        ORDER_FULFILLED: "Order fulfilled",
        ORDER_METADATA_UPDATED: "Order metadata updated",
        DRAFT_ORDER_CREATED: "Draft order created",
        DRAFT_ORDER_UPDATED: "Draft order updated",
        DRAFT_ORDER_DELETED: "Draft order deleted",
        SALE_CREATED: "Sale created",
        SALE_UPDATED: "Sale updated",
        SALE_DELETED: "Sale deleted",
        SALE_TOGGLE: "Sale toggle",
        INVOICE_REQUESTED: "Invoice requested",
        INVOICE_DELETED: "Invoice deleted",
        INVOICE_SENT: "Invoice sent",
        CUSTOMER_CREATED: "Customer created",
        CUSTOMER_UPDATED: "Customer updated",
        CUSTOMER_DELETED: "Customer deleted",
        CUSTOMER_METADATA_UPDATED: "Customer metadata updated",
        COLLECTION_CREATED: "Collection created",
        COLLECTION_UPDATED: "Collection updated",
        COLLECTION_DELETED: "Collection deleted",
        COLLECTION_METADATA_UPDATED: "Collection metadata updated",
        PRODUCT_CREATED: "Product created",
        PRODUCT_UPDATED: "Product updated",
        PRODUCT_DELETED: "Product deleted",
        PRODUCT_MEDIA_CREATED: "Product media created",
        PRODUCT_MEDIA_UPDATED: "Product media updated",
        PRODUCT_MEDIA_DELETED: "Product media deleted",
        PRODUCT_METADATA_UPDATED: "Product metadata updated",
        PRODUCT_VARIANT_CREATED: "Product variant created",
        PRODUCT_VARIANT_UPDATED: "Product variant updated",
        PRODUCT_VARIANT_DELETED: "Product variant deleted",
        PRODUCT_VARIANT_METADATA_UPDATED: "Product variant metadata updated",
        PRODUCT_VARIANT_OUT_OF_STOCK: "Product variant stock changed",
        PRODUCT_VARIANT_BACK_IN_STOCK: "Product variant back in stock",
        PRODUCT_VARIANT_STOCK_UPDATED: "Product variant stock updated",
        CHECKOUT_CREATED: "Checkout created",
        CHECKOUT_UPDATED: "Checkout updated",
        CHECKOUT_METADATA_UPDATED: "Checkout metadata updated",
        FULFILLMENT_CREATED: "Fulfillment created",
        FULFILLMENT_CANCELED: "Fulfillment cancelled",
        FULFILLMENT_APPROVED: "Fulfillment approved",
        FULFILLMENT_METADATA_UPDATED: "Fulfillment metadata updated",
        NOTIFY_USER: "Notify user",
        PAGE_CREATED: "Page Created",
        PAGE_UPDATED: "Page Updated",
        PAGE_DELETED: "Page Deleted",
        PAGE_TYPE_CREATED: "Page type created",
        PAGE_TYPE_UPDATED: "Page type updated",
        PAGE_TYPE_DELETED: "Page type deleted",
        PERMISSION_GROUP_CREATED: "Permission group created",
        PERMISSION_GROUP_UPDATED: "Permission group updated",
        PERMISSION_GROUP_DELETED: "Permission group deleted",
        SHIPPING_PRICE_CREATED: "Shipping price created",
        SHIPPING_PRICE_UPDATED: "Shipping price updated",
        SHIPPING_PRICE_DELETED: "Shipping price deleted",
        SHIPPING_ZONE_CREATED: "Shipping zone created",
        SHIPPING_ZONE_UPDATED: "Shipping zone updated",
        SHIPPING_ZONE_DELETED: "Shipping zone deleted",
        SHIPPING_ZONE_METADATA_UPDATED: "Shipping zone metadata updated",
        STAFF_CREATED: "Staff created",
        STAFF_UPDATED: "Staff updated",
        STAFF_DELETED: "Staff deleted",
        TRANSACTION_ACTION_REQUEST: "Payment action request",
        TRANSACTION_ITEM_METADATA_UPDATED: "Transaction item metadata updated",
        TRANSLATION_CREATED: "Create translation",
        TRANSLATION_UPDATED: "Update translation",
        WAREHOUSE_CREATED: "Warehouse created",
        WAREHOUSE_UPDATED: "Warehouse updated",
        WAREHOUSE_DELETED: "Warehouse deleted",
        WAREHOUSE_METADATA_UPDATED: "Warehouse metadata updated",
        VOUCHER_CREATED: "Voucher created",
        VOUCHER_UPDATED: "Voucher updated",
        VOUCHER_DELETED: "Voucher deleted",
        VOUCHER_METADATA_UPDATED: "Voucher metadata updated",
        OBSERVABILITY: "Observability",
        THUMBNAIL_CREATED: "Thumbnail created",
    }

    CHOICES = [
        (ANY, DISPLAY_LABELS[ANY]),
        (ADDRESS_CREATED, DISPLAY_LABELS[ADDRESS_CREATED]),
        (ADDRESS_UPDATED, DISPLAY_LABELS[ADDRESS_UPDATED]),
        (ADDRESS_DELETED, DISPLAY_LABELS[ADDRESS_DELETED]),
        (APP_INSTALLED, DISPLAY_LABELS[APP_INSTALLED]),
        (APP_UPDATED, DISPLAY_LABELS[APP_UPDATED]),
        (APP_DELETED, DISPLAY_LABELS[APP_DELETED]),
        (APP_STATUS_CHANGED, DISPLAY_LABELS[APP_STATUS_CHANGED]),
        (ATTRIBUTE_CREATED, DISPLAY_LABELS[ATTRIBUTE_CREATED]),
        (ATTRIBUTE_UPDATED, DISPLAY_LABELS[ATTRIBUTE_UPDATED]),
        (ATTRIBUTE_DELETED, DISPLAY_LABELS[ATTRIBUTE_DELETED]),
        (ATTRIBUTE_VALUE_CREATED, DISPLAY_LABELS[ATTRIBUTE_VALUE_CREATED]),
        (ATTRIBUTE_VALUE_UPDATED, DISPLAY_LABELS[ATTRIBUTE_VALUE_UPDATED]),
        (ATTRIBUTE_VALUE_DELETED, DISPLAY_LABELS[ATTRIBUTE_VALUE_DELETED]),
        (CATEGORY_CREATED, DISPLAY_LABELS[CATEGORY_CREATED]),
        (CATEGORY_UPDATED, DISPLAY_LABELS[CATEGORY_UPDATED]),
        (CATEGORY_DELETED, DISPLAY_LABELS[CATEGORY_DELETED]),
        (CHANNEL_CREATED, DISPLAY_LABELS[CHANNEL_CREATED]),
        (CHANNEL_UPDATED, DISPLAY_LABELS[CHANNEL_UPDATED]),
        (CHANNEL_DELETED, DISPLAY_LABELS[CHANNEL_DELETED]),
        (CHANNEL_STATUS_CHANGED, DISPLAY_LABELS[CHANNEL_STATUS_CHANGED]),
        (GIFT_CARD_CREATED, DISPLAY_LABELS[GIFT_CARD_CREATED]),
        (GIFT_CARD_UPDATED, DISPLAY_LABELS[GIFT_CARD_UPDATED]),
        (GIFT_CARD_DELETED, DISPLAY_LABELS[GIFT_CARD_DELETED]),
        (GIFT_CARD_STATUS_CHANGED, DISPLAY_LABELS[GIFT_CARD_STATUS_CHANGED]),
        (GIFT_CARD_METADATA_UPDATED, DISPLAY_LABELS[GIFT_CARD_METADATA_UPDATED]),
        (MENU_CREATED, DISPLAY_LABELS[MENU_CREATED]),
        (MENU_UPDATED, DISPLAY_LABELS[MENU_UPDATED]),
        (MENU_DELETED, DISPLAY_LABELS[MENU_DELETED]),
        (MENU_ITEM_CREATED, DISPLAY_LABELS[MENU_ITEM_CREATED]),
        (MENU_ITEM_UPDATED, DISPLAY_LABELS[MENU_ITEM_UPDATED]),
        (MENU_ITEM_DELETED, DISPLAY_LABELS[MENU_ITEM_DELETED]),
        (ORDER_CREATED, DISPLAY_LABELS[ORDER_CREATED]),
        (ORDER_CONFIRMED, DISPLAY_LABELS[ORDER_CONFIRMED]),
   