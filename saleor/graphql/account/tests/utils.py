from ...core.utils import snake_to_camel_case


def convert_dict_keys_to_camel_case(d):
    """Changes dict fields from d[field_name] to d[fieldName].

    Useful when dealing with dict data such as address that need to be parsed
    into graphql input.
    