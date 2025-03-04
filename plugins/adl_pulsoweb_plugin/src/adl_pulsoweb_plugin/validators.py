import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def validate_start_date(value: datetime.datetime):
    """
    Validate the start date for data collection.

    The start date should be in the past.

    :param datetime value: The start date.
    :return: None
    :raises: ValidationError
    """
    if value is not None and value > timezone.now():
        raise ValidationError(_("Start date should be in the past"))
