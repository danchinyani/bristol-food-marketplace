from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Producer, Customer, Product, Recipe, RecurringOrder
import datetime


def build_delivery_day_choices(recurrence_day):
    try:
        recurrence_day = int(recurrence_day)
    except (TypeError, ValueError):
        recurrence_day = 0

    choices = []
    for week_offset, prefix in ((0, 'Same week'), (1, 'Next week')):
        for weekday_value, weekday_label in RecurringOrder.WEEKDAY_CHOICES:
            if week_offset == 0:
                day_gap = weekday_value - recurrence_day
            else:
                day_gap = (7 - recurrence_day) + weekday_value

            if day_gap >= 2:
                choices.append((f'{week_offset}:{weekday_value}', f'{prefix} - {weekday_label}'))

    return choices


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data if item]
        cleaned_file = single_file_clean(data, initial)
        return [cleaned_file] if cleaned_file else []

class ProducerSignupForm(forms.ModelForm):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    
    class Meta:
        model = Producer
        fields = ['business_name', 'contact_name', 'email', 'phone_number', 'business_address', 'postcode']

    # ENFORCE AUTH_PASSWORD_VALIDATORS BEFORE THE USER IS CREATED
    def clean_password(self):
        password = self.cleaned_data.get('password')
        try:
            validate_password(password)
        except ValidationError as e:
            raise forms.ValidationError(e.messages)
        return password

    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password'],
            email=self.cleaned_data['email']
        )
        producer = super().save(commit=False)
        producer.user = user
        if commit:
            producer.save()
        return producer

class CustomerSignupForm(forms.ModelForm):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    
    class Meta:
        model = Customer
        fields = ['name', 'email', 'phone_number', 'address', 'postcode']

    # ENFORCE AUTH_PASSWORD_VALIDATORS BEFORE THE USER IS CREATED
    def clean_password(self):
        password = self.cleaned_data.get('password')
        try:
            validate_password(password)
        except ValidationError as e:
            raise forms.ValidationError(e.messages)
        return password

    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password'],
            email=self.cleaned_data['email']
        )
        customer = super().save(commit=False)
        customer.user = user
        if commit:
            customer.save()
        return customer
#edit account
class ChangeEmailForm(forms.Form):
    email = forms.EmailField(label="New Email")


class ChangePostcodeForm(forms.Form):
    postcode = forms.CharField(
        max_length=7,
        min_length=5,
        label="New Postcode"
    )

class ProducerBioForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bio'].widget.attrs.update({'class': 'auth-field', 'rows': 6})
        self.fields['bio'].label = 'About your business'

    class Meta:
        model = Producer
        fields = ['bio']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 6}),
        }


class ProductForm(forms.ModelForm):
    # ALLERGEN FIELD - STORES ZERO, ONE, OR MANY
    allergens = forms.MultipleChoiceField(
        choices=Product.ALLERGEN_CHOICES,
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'producer-allergen-select', 'size': 8}),
    )

    def clean(self):
        cleaned_data = super().clean()
        is_surplus = cleaned_data.get('is_surplus')
        discount_percent = cleaned_data.get('discount_percent') or 0

        if not is_surplus and discount_percent > 0:
            self.add_error('discount_percent', 'Discount can only be applied to surplus produce.')

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # PRE-POPULATE THE ALLERGEN LIST WHEN EDITING AN EXISTING PRODUCT
        if self.instance and self.instance.pk:
            self.fields['allergens'].initial = self.instance.allergens

        for field_name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                # PRESERVE EXISTING CLASSES WHILE ADDING THE STANDARD AUTH FIELD CLASS
                existing_classes = field.widget.attrs.get('class', '')
                combined_classes = f"{existing_classes} auth-field".strip()
                field.widget.attrs.update({'class': combined_classes})

    class Meta:
        model = Product
        fields = [
            'name',
            'category',
            'description',
            'price',
            'unit',
            'stock_quantity',
            'seasonal_from',
            'seasonal_to',
            'is_organic',
            'allergens',
            'is_surplus',
            'discount_percent',
            'image',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'discount_percent': forms.NumberInput(attrs={'min': 0, 'max': 100}),

        }

    def clean_allergens(self):
        # VALIDATE THAT ONLY SUPPORTED ALLERGEN KEYS ARE SUBMITTED
        selected_allergens = self.cleaned_data.get('allergens', [])
        valid_allergens = {choice[0] for choice in Product.ALLERGEN_CHOICES}
        return [allergen for allergen in selected_allergens if allergen in valid_allergens]

    def save(self, commit=True):
        # SAVE THE PRODUCT WITH THE SELECTED ALLERGEN LIST IN THE JSON FIELD
        product = super().save(commit=False)
        product.allergens = self.cleaned_data.get('allergens', [])
        if commit:
            product.save()
        return product


# CHECKOUT FORM - COLLECTS DELIVERY DATE AND PAYMENT DETAILS FROM THE CUSTOMER AT CHECKOUT
class CheckoutForm(forms.Form):
    # PREFERRED DATE THE CUSTOMER WOULD LIKE TO RECEIVE THEIR ORDER
    preferred_delivery_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'auth-field', 'type': 'date'}),
        label='Preferred Delivery Date',
    )

    # OPTIONAL RECURRING ORDER CONTROLS SHOWN DURING CHECKOUT
    make_recurring = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'basket-recurring-checkbox'}),
        label='Make this a recurring order',
    )

    recurrence_frequency = forms.ChoiceField(
        choices=RecurringOrder.FREQUENCY_CHOICES,
        required=False,
        initial='WEEKLY',
        widget=forms.Select(attrs={'class': 'auth-field'}),
        label='Recurrence Frequency',
    )

    recurrence_day = forms.ChoiceField(
        choices=RecurringOrder.WEEKDAY_CHOICES,
        required=False,
        initial=0,
        widget=forms.Select(attrs={'class': 'auth-field'}),
        label='Recurrence Day',
    )

    recurring_delivery_day = forms.ChoiceField(
        choices=[],
        required=False,
        initial='0:2',
        widget=forms.Select(attrs={'class': 'auth-field'}),
        label='Recurring Delivery Day',
    )

    # CARD HOLDER NAME AS IT APPEARS ON THE CARD
    card_holder_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'auth-field', 'placeholder': 'Name on card'}),
        label='Card Holder Name',
    )

    # FULL CARD NUMBER - ONLY THE LAST 4 DIGITS WILL BE SAVED TO THE DATABASE
    card_number = forms.CharField(
        max_length=19,
        required=False,
        widget=forms.TextInput(attrs={'class': 'auth-field', 'placeholder': '1234 5678 9012 3456', 'autocomplete': 'off'}),
        label='Card Number',
    )

    # CARD EXPIRY DATE IN MM/YY FORMAT
    card_expiry = forms.CharField(
        max_length=5,
        required=False,
        widget=forms.TextInput(attrs={'class': 'auth-field', 'placeholder': 'MM/YY'}),
        label='Expiry Date',
    )

    # CVV SECURITY CODE - NEVER STORED, ONLY USED FOR VALIDATION DISPLAY
    card_cvv = forms.CharField(
        max_length=4,
        required=False,
        widget=forms.TextInput(attrs={'class': 'auth-field', 'placeholder': '123', 'autocomplete': 'off'}),
        label='CVV',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.is_bound:
            recurrence_day = self.data.get('recurrence_day', self.fields['recurrence_day'].initial)
        else:
            recurrence_day = self.initial.get('recurrence_day', self.fields['recurrence_day'].initial)

        self.fields['recurring_delivery_day'].choices = build_delivery_day_choices(recurrence_day)

    def clean_card_number(self):
        # STRIP SPACES AND VALIDATE THAT THE CARD NUMBER IS NUMERIC AND 16 DIGITS
        number = self.cleaned_data.get('card_number', '').replace(' ', '').replace('-', '')
        if not number:
            return ''
        if not number.isdigit() or len(number) != 16:
            raise forms.ValidationError('Please enter a valid 16-digit card number.')
        return number

    def clean_preferred_delivery_date(self):
        # ENSURE THE PREFERRED DELIVERY DATE IS NOT IN THE PAST
        date = self.cleaned_data['preferred_delivery_date']
        if date < datetime.date.today():
            raise forms.ValidationError('Preferred delivery date cannot be in the past.')
        return date

    def clean_card_expiry(self):
        # VALIDATE EXPIRY FORMAT IS MM/YY
        expiry = self.cleaned_data.get('card_expiry', '')
        if not expiry:
            return ''
        if len(expiry) != 5 or expiry[2] != '/' or not expiry[:2].isdigit() or not expiry[3:].isdigit():
            raise forms.ValidationError('Please enter expiry in MM/YY format.')
        return expiry

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('make_recurring'):
            return cleaned_data

        preferred_delivery_date = cleaned_data.get('preferred_delivery_date')
        minimum_date = datetime.date.today() + datetime.timedelta(days=2)

        if preferred_delivery_date and preferred_delivery_date < minimum_date:
            self.add_error(
                'preferred_delivery_date',
                'Recurring orders require the first delivery date to be at least 48 hours from today.'
            )

        if not cleaned_data.get('recurrence_frequency'):
            self.add_error('recurrence_frequency', 'Please choose how often this order should repeat.')

        if cleaned_data.get('recurrence_day') in (None, ''):
            self.add_error('recurrence_day', 'Please choose which day the recurring order should run.')

        if cleaned_data.get('recurring_delivery_day') in (None, ''):
            self.add_error('recurring_delivery_day', 'Please choose the recurring delivery day.')
            return cleaned_data

        valid_delivery_choices = {
            value for value, _label in build_delivery_day_choices(cleaned_data.get('recurrence_day'))
        }
        if cleaned_data.get('recurring_delivery_day') not in valid_delivery_choices:
            self.add_error(
                'recurring_delivery_day',
                'Recurring delivery must be at least 48 hours after the recurrence day.'
            )

        return cleaned_data
    
class RecipeForm(forms.ModelForm):
    images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={'class': 'auth-field', 'accept': 'image/*'}),
        label='Recipe Images (upload one or more)'
    )

    linked_products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label='Link to your products'
    )

    def __init__(self, producer=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if producer:
            self.fields['linked_products'].queryset = Product.objects.filter(producer=producer)
        for field_name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs.update({'class': 'auth-field'})


    class Meta:
        model = Recipe
        fields = ['title', 'description', 'ingredients', 'instructions', 'seasonal_tag', 'linked_products']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'ingredients': forms.Textarea(attrs={'rows': 5}),
            'instructions': forms.Textarea(attrs={'rows': 6}),
        }