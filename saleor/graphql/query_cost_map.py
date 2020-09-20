"""Costs map used by query complexity validator.

It's three levels deep dict of dicts:

- Type
- Fields
- Complexity

To set complexity cost for querying a field "likes" on type "User":

{
    "User": {
        "likes": {"complexity": 2}
    }
}

Querying above field will not increase query complexity by 1.

If field's complexity should be multiplied by value of argument (or arguments),
you can specify names of those arguments in "multipliers" list:

{
    "Query": {
        "products": {"complexity": 1, "multipliers": ["first", "last"]}
    }
}

This will result in following queries having cost of 100:

{ products(first: 100) { edges: { id } } }

{ products(last: 100) { edges: { id } } }

{ products(first: 10, last: 10) { edges: { id } } }

Notice that complexity is in last case is multiplied by all arguments.

Complexity is also multiplied recursively:

{
    "Query": {
        "products": {"complexity": 1, "multipliers": ["first", "last"]}
    },
    "Product": {
        "shippings": {"complexity": 1},
    }
}

This query will have cost of 200 (100 x 2 for each product):

{ products(first: 100) { complexity } }
"""

COST_MAP = {
    "Query": {
        "address": {"complexity": 1},
        "addressValidationRules": {"complexity": 1},
        "app": {"complexity": 1},
        "appExtension": {"complexity": 1},
        "appExtensions": {"complexity": 1, "multipliers": ["first", "last"]},
        "apps": {"complexity": 1, "multipliers": ["first", "last"]},
        "appsInstallations": {"complexity": 1},
        "attribute": {"complexity": 1},
        "attributes": {"complexity": 1, "multipliers": ["first", "last"]},
        "categories": {"complexity": 1, "multipliers": ["first", "last"]},
        "category": {"complexity": 1},
        "channel": {"complexity": 1},
        "channels": {"complexity": 1},
        "checkout": {"complexity": 1},
        "checkoutLines": {"complexity": 1, "multipliers": ["first", "last"]},
        "checkouts": {"complexity": 1, "multipliers": ["first", "last"]},
        "collection": {"complexity": 1},
        "collections": {"complexity": 1, "multipliers": ["first", "last"]},
        "customers": {"complexity": 1, "multipliers": ["first", "last"]},
        "digitalContent": {"complexity": 1},
        "digitalContents": {"complexity": 1, "multipliers": ["first", "last"]},
        "draftOrders": {"complexity": 1, "multipliers": ["first", "last"]},
        "exportFile": {"complexity": 1},
        "exportFiles": {"complexity": 1, "multipliers": ["first", "last"]},
        "giftCard": {"complexity": 1},
        "giftCardCurrencies": {"complexity": 1},
        "giftCards": {"complexity": 1, "multipliers": ["first", "last"]},
        "giftCardTags": {"complexity": 1, "multipliers": ["first", "last"]},
        "homepageEvents": {"complexity": 1, "multipliers": ["first", "last"]},
        "me": {"complexity": 1},
        "menu": {"complexity": 1},
        "menuItem": {"complexity": 1},
        "menuItems": {"complexity": 1, "multipliers": ["first", "last"]},
        "menus": {"complexity": 1, "multipliers": ["first", "last"]},
        "order": {"complexity": 1},
        "orderByToken": {"complexity": 1},
        "orders": {"complexity": 1, "multipliers": ["first", "last"]},
        "ordersTotal": {"complexity": 1},
        "page": {"complexity": 1},
        "pages": {"complexity": 1, "multipliers": ["first", "last"]},
        "pageType": {"complexity": 1},
        "pageTypes": {"complexity": 1, "multipliers": ["first", "last"]},
        "payment": {"complexity": 1},
        "payments": {"complexity": 1, "multipliers": ["first", "last"]},
        "permissionGroup": {"complexity": 1},
        "permissionGroups": {"complexity": 1, "multipliers": ["first", "last"]},
        "plugin": {"complexity": 1},
        "plugins": {"complexity": 1, "multipliers": ["first", "last"]},
        "product": {"complexity": 1},
        "products": {"complexity": 1, "multipliers": ["first", "last"]},
        "productType": {"complexity": 1},
        "productTypes": {"complexity": 1, "multipliers": ["first", "last"]},
        "productVariant": {"complexity": 1},
        "productVariants": {"complexity": 1, "multipliers": ["first", "last"]},
        "sale": {"complexity": 1},
        "sales": {"complexity": 1, "multipliers": ["first", "last"]},
        "shippingZone": {"complexity