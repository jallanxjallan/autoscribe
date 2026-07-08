from asc.state.slugmap import SlugMap


def list_control_slugs() -> list[str]:
    return SlugMap().list_slugs()