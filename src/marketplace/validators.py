import re
from django.core.exceptions import ValidationError


# ENFORCES AT LEAST ONE SPECIAL CHARACTER IN THE PASSWORD
class SpecialCharacterValidator:
    SPECIAL_CHARS = r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;\'`~/]'

    def validate(self, password, user=None):
        if not re.search(self.SPECIAL_CHARS, password):
            raise ValidationError(self.get_help_text())

    def get_help_text(self):
        return 'Your password must contain at least one special character (e.g. !@#$%^&*).'
