"""The app's idea of 'today'. Tests replace `today` to move the calendar."""

from datetime import date


def today() -> date:
    return date.today()
