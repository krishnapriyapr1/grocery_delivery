from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, Order, Product, Category, DeliveryBoy

class UserRegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    phone = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    address = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'address', 'password1', 'password2']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken. Please choose another one.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email address is already registered.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name')
        user.last_name = self.cleaned_data.get('last_name')
        user.email = self.cleaned_data.get('email')
        if commit:
            user.save()
        return user

class SupplierRegistrationForm(UserCreationForm):
    company_name = forms.CharField(max_length=100)
    address = forms.CharField(max_length=200)
    phone = forms.CharField(max_length=20)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['address', 'phone', 'profile_picture']
        widgets = {
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'required': 'required'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'required': 'required'}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'})
        }

class OrderForm(forms.ModelForm):
    PAYMENT_CHOICES = [
        ('cod', 'Cash on Delivery'),
        ('card', 'Credit/Debit Card'),
        ('upi', 'UPI'),
        ('wallet', 'Digital Wallet')
    ]
    
    name = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(max_length=15, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    address = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), required=True)
    city = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    postal_code = forms.CharField(max_length=10, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    payment_method = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        required=True,
        initial='cod',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    
    class Meta:
        model = Order
        fields = ['name', 'email', 'phone', 'address', 'city', 'postal_code', 'payment_method']

    def clean_payment_method(self):
        payment_method = self.cleaned_data.get('payment_method')
        if not payment_method:
            raise forms.ValidationError("Please select a payment method.")
        return payment_method

class SearchForm(forms.Form):
    query = forms.CharField(max_length=100, required=False)
    category = forms.CharField(max_length=100, required=False)

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter category name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter category description'}),
        }

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'category', 'supplier', 'description', 'price', 'stock', 'image', 'is_available']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter product name',
                'required': 'required'
            }),
            'category': forms.Select(attrs={
                'class': 'form-control',
                'required': 'required'
            }),
            'supplier': forms.Select(attrs={
                'class': 'form-control',
                'required': 'required'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter product description',
                'required': 'required'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
                'required': 'required'
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'required': 'required'
            }),
            'is_available': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price <= 0:
            raise forms.ValidationError("Price must be greater than zero")
        return price

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock < 0:
            raise forms.ValidationError("Stock cannot be negative")
        return stock

class DeliveryBoyRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20)
    address = forms.CharField(max_length=200)
    vehicle_number = forms.CharField(max_length=20, required=False)
    vehicle_type = forms.CharField(max_length=50, required=False)
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def save(self, commit=True):
        if not commit:
            return super().save(commit=False)
            
        user = super().save()
        delivery_boy = DeliveryBoy.objects.create(
            user=user,
            name=f"{user.first_name} {user.last_name}",
            phone=self.cleaned_data['phone'],
            address=self.cleaned_data['address'],
            vehicle_number=self.cleaned_data['vehicle_number'],
            vehicle_type=self.cleaned_data['vehicle_type']
        )
        return user
