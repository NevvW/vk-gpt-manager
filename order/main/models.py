from django.db import models

# Create your models here.
class Bot(models.Model):
    interval_first = models.FloatField()
    interval_second = models.FloatField()
    key_word = models.TextField()
    ban_word = models.TextField()
    agent_promt = models.TextField()
    promt = models.TextField()
    text_one_remember = models.TextField()
    text_two_remember = models.TextField()
    proxy_host = models.CharField()
    proxy_port = models.CharField()
    proxy_user = models.CharField()
    proxy_password = models.CharField()