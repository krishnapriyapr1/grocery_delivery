from django.db import migrations, models

def add_quick_messages(apps, schema_editor):
    QuickMessage = apps.get_model('store', 'QuickMessage')
    
    # Quick messages for customers
    customer_messages = [
        "Hi, where are you currently?",
        "Please deliver to the gate",
        "I'll be there in 5 minutes",
        "Please call when you arrive",
        "Can you please hurry?",
        "Is there any delay?"
    ]
    
    # Quick messages for delivery boys
    delivery_messages = [
        "I'm on my way",
        "I've reached your location",
        "Traffic delay, will be late by 10 minutes",
        "Please provide landmark",
        "I'm at the gate",
        "Unable to find your address"
    ]
    
    # Only add messages if they don't exist
    for msg in customer_messages:
        if not QuickMessage.objects.filter(message=msg, is_for_customer=True).exists():
            QuickMessage.objects.create(message=msg, is_for_customer=True)
    
    for msg in delivery_messages:
        if not QuickMessage.objects.filter(message=msg, is_for_customer=False).exists():
            QuickMessage.objects.create(message=msg, is_for_customer=False)

def remove_quick_messages(apps, schema_editor):
    QuickMessage = apps.get_model('store', 'QuickMessage')
    QuickMessage.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('store', '0010_quickmessage_deliverychat'),
    ]

    operations = [
        migrations.RunPython(add_quick_messages, remove_quick_messages),
    ]
