from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.utils.text import slugify
import uuid
from django.db.models import Sum, Avg
from datetime import timedelta

# Create your models here.

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='category_images/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            unique_slug = base_slug
            counter = 1
            
            # Keep trying until we find a unique slug
            while True:
                try:
                    # Check if a category with this slug already exists
                    if not Category.objects.filter(slug=unique_slug).exists():
                        self.slug = unique_slug
                        break
                    # If it exists, try the next counter value
                    unique_slug = f"{base_slug}-{counter}"
                    counter += 1
                except Exception:
                    # If any error occurs, generate a unique slug using timestamp
                    unique_slug = f"{base_slug}-{int(timezone.now().timestamp())}"
                    self.slug = unique_slug
                    break
        
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Supplier(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='products')
    stock = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=3)
    image = models.ImageField(upload_to='products/')
    is_available = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    approval_status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    _has_pending_restock = None

    def __str__(self):
        return self.name

    def needs_reorder(self):
        return self.stock <= self.reorder_level

    @property
    def has_pending_restock(self):
        if self._has_pending_restock is None:
            self._has_pending_restock = self.restock_requests.filter(status='pending').exists()
        return self._has_pending_restock

    @has_pending_restock.setter
    def has_pending_restock(self, value):
        self._has_pending_restock = value

class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_total(self):
        return sum(item.total_price() for item in self.items.all())

    def __str__(self):
        return f"Cart for {self.user.username}"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def total_price(self):
        return self.quantity * self.product.price

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ]
    
    PAYMENT_CHOICES = [
        ('cod', 'Cash on Delivery'),
        ('card', 'Credit/Debit Card'),
        ('upi', 'UPI'),
        ('wallet', 'Digital Wallet')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cod')
    payment_status = models.CharField(max_length=20, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    tracking_number = models.CharField(max_length=50, blank=True, null=True)
    estimated_delivery = models.DateTimeField(null=True, blank=True)
    stripe_charge_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_unread_messages_count(self, for_customer=True):
        """Get count of unread messages for either customer or delivery boy"""
        if not hasattr(self, 'delivery_assignment'):
            return 0
        return DeliveryChat.objects.filter(
            order=self,
            is_from_customer=not for_customer,
            is_read=False
        ).count()

    def get_total_with_delivery(self):
        """Get total amount including delivery fee"""
        delivery_fee = 40 if self.total_amount < 500 else 0
        return self.total_amount + delivery_fee

    def update_status(self, new_status):
        """Update order status and handle related tasks"""
        if new_status != self.status:
            self.status = new_status
            if new_status == 'delivered':
                self.check_and_send_rewards()
            self.save()

    def check_and_send_rewards(self):
        """Check if user qualifies for rewards and send if eligible"""
        from datetime import datetime, timedelta
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_orders = Order.objects.filter(
            user=self.user,
            status='delivered',
            created_at__gte=month_start
        )
        total_spend = sum(order.total_amount for order in month_orders)
        if total_spend >= 1000:
            from .views import create_customer_coupon
            create_customer_coupon(self.user.id, total_spend)

    def __str__(self):
        return f"Order #{self.id} by {self.user.username}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def get_cost(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

class RestockRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='restock_requests')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='restock_requests')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Restock request for {self.product.name} - {self.get_status_display()}"

    class Meta:
        ordering = ['-created_at']

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('restock_request', 'Restock Request'),
        ('stock_update', 'Stock Update'),
        ('approval', 'Approval')
    ]
    
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type}: {self.title}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True)

    def __str__(self):
        return self.user.username

class SupplierActivity(models.Model):
    ACTIVITY_TYPES = [
        ('restock_request', 'Restock Request'),
        ('restock_completed', 'Restock Completed'),
        ('restock_rejected', 'Restock Rejected'),
        ('stock_update', 'Stock Update'),
        ('approval_status', 'Approval Status Change')
    ]
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Supplier Activities'

    def __str__(self):
        return f"{self.supplier.name} - {self.activity_type} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

class SupplierMessage(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    is_from_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        direction = "Admin to Supplier" if self.is_from_admin else "Supplier to Admin"
        return f"{direction} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    minimum_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.code} - ₹{self.discount_amount} off"

    @property
    def is_valid(self):
        now = timezone.now()
        return (
            self.is_active and
            not self.is_used and 
            self.valid_from <= now <= self.valid_to
        )

    class Meta:
        ordering = ['-created_at']

class DeliveryBoy(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    is_available = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    total_deliveries = models.IntegerField(default=0)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    vehicle_number = models.CharField(max_length=20, blank=True)
    vehicle_type = models.CharField(max_length=50, blank=True)
    id_proof = models.FileField(upload_to='delivery_boy_docs/', blank=True)
    
    def __str__(self):
        return self.name
        
    def update_metrics(self):
        """Update delivery boy metrics based on completed deliveries"""
        completed_deliveries = self.assignments.filter(status='delivered')
        self.total_deliveries = completed_deliveries.count()
        avg_rating = completed_deliveries.filter(rating__isnull=False).aggregate(Avg('rating'))['rating__avg']
        self.avg_rating = round(float(avg_rating or 0), 2)
        self.save()

class DeliveryAssignment(models.Model):
    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('picked_up', 'Picked Up'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed')
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='delivery_assignment')
    delivery_boy = models.ForeignKey(DeliveryBoy, on_delete=models.SET_NULL, null=True, related_name='assignments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')
    assigned_at = models.DateTimeField(auto_now_add=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True)
    rating = models.IntegerField(null=True, blank=True, choices=[
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars')
    ])

    def __str__(self):
        return f"Order #{self.order.id} - {self.delivery_boy.name}"

class DeliveryBoyReport(models.Model):
    delivery_boy = models.ForeignKey(DeliveryBoy, on_delete=models.CASCADE, related_name='reports')
    date = models.DateField()
    orders_delivered = models.PositiveIntegerField(default=0)
    on_time_deliveries = models.PositiveIntegerField(default=0)
    total_distance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        unique_together = ['delivery_boy', 'date']

    def __str__(self):
        return f"Report for {self.delivery_boy.name} on {self.date}"

class DeliveryChat(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='chats')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='delivery_chats')
    delivery_boy = models.ForeignKey(DeliveryBoy, on_delete=models.CASCADE, related_name='delivery_chats')
    message = models.TextField()
    is_from_customer = models.BooleanField(default=True)
    is_quick_message = models.BooleanField(default=False)
    is_system_message = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Chat message for Order #{self.order.id}"

class QuickMessage(models.Model):
    message = models.CharField(max_length=200)
    is_for_customer = models.BooleanField(default=True)
    
    def __str__(self):
        return self.message
