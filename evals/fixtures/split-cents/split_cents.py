def split_cents(total: int, people: int) -> list[int]:
    """Split cents evenly, assigning remainder cents from the first person onward."""
    share, remainder = divmod(total, people)
    return [share + (index < remainder) for index in range(people)]
