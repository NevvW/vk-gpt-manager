from django.db import models

# Create your models here.
class Bot(models.Model):
    interval_first = models.FloatField()
    interval_second = models.FloatField()
    key_word = models.TextField()
    ban_word = models.TextField()
    agent_promt = models.TextField()
    promt = models.FileField(upload_to='uploads/', blank=True, null=True)
    text_one_remember = models.TextField()
    text_two_remember = models.TextField()
    proxy_host = models.TextField()
    proxy_port = models.TextField()
    proxy_user = models.TextField()
    proxy_password = models.TextField()
    last_change = models.DateTimeField(blank=True, null=True)