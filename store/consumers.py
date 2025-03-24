import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Order, DeliveryChat

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Join a group for each order the user is involved with
        self.order_groups = []
        orders = await self.get_user_orders()
        
        for order in orders:
            group_name = f"chat_{order.id}"
            self.order_groups.append(group_name)
            await self.channel_layer.group_add(
                group_name,
                self.channel_name
            )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave all order groups
        for group_name in self.order_groups:
            await self.channel_layer.group_discard(
                group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')
        
        if message_type == 'chat_message':
            order_id = text_data_json['order_id']
            message = text_data_json['message']
            
            # Save the message to database
            chat = await self.save_chat_message(order_id, message)
            if chat:
                # Send message to the order group
                await self.channel_layer.group_send(
                    f"chat_{order_id}",
                    {
                        'type': 'chat_message',
                        'message': message,
                        'order_id': order_id,
                        'is_from_customer': True,
                        'timestamp': chat.created_at.strftime('%I:%M %p')
                    }
                )
    
    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'order_id': event['order_id'],
            'is_from_customer': event['is_from_customer'],
            'timestamp': event['timestamp']
        }))
    
    @database_sync_to_async
    def get_user_orders(self):
        if hasattr(self.user, 'deliveryboy'):
            # For delivery boys, get their assigned orders
            return list(Order.objects.filter(
                delivery_assignment__delivery_boy=self.user.deliveryboy,
                status__in=['processing', 'shipped']
            ))
        else:
            # For customers, get their active orders
            return list(Order.objects.filter(
                user=self.user,
                status__in=['processing', 'shipped']
            ))
    
    @database_sync_to_async
    def save_chat_message(self, order_id, message):
        try:
            order = Order.objects.get(id=order_id)
            if not hasattr(order, 'delivery_assignment'):
                return None
                
            # Check if user is authorized to send message
            if (self.user == order.user or 
                (hasattr(self.user, 'deliveryboy') and 
                 self.user.deliveryboy == order.delivery_assignment.delivery_boy)):
                
                chat = DeliveryChat.objects.create(
                    order=order,
                    customer=order.user,
                    delivery_boy=order.delivery_assignment.delivery_boy,
                    message=message,
                    is_from_customer=self.user == order.user
                )
                return chat
                
        except Order.DoesNotExist:
            pass
        return None
