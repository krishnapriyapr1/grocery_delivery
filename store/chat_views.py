from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
import json
from .models import Order, DeliveryChat, QuickMessage

@login_required
@require_http_methods(["POST"])
def send_chat_message(request):
    data = json.loads(request.body)
    order_id = data.get('order_id')
    message = data.get('message')
    is_quick_message = data.get('is_quick_message', False)
    
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if not hasattr(order, 'delivery_assignment'):
        return JsonResponse({'status': 'error', 'message': 'No delivery boy assigned yet'})
    
    chat = DeliveryChat.objects.create(
        order=order,
        customer=request.user,
        delivery_boy=order.delivery_assignment.delivery_boy,
        message=message,
        is_from_customer=True,
        is_quick_message=is_quick_message
    )
    
    return JsonResponse({
        'status': 'success',
        'message': 'Message sent successfully',
        'chat': {
            'id': chat.id,
            'message': chat.message,
            'created_at': chat.created_at.strftime('%I:%M %p')
        }
    })

@login_required
def get_quick_messages(request):
    messages = QuickMessage.objects.filter(is_for_customer=True)
    return JsonResponse({
        'status': 'success',
        'messages': list(messages.values('id', 'message'))
    })
