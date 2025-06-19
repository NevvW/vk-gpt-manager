from django import forms
from .models import Bot

class BotForm(forms.Form):
    interval_first = forms.FloatField(required=True)
    interval_second = forms.FloatField(required=True)
    key_word = forms.CharField(widget=forms.Textarea(attrs={"rows":"5"}))
    ban_word = forms.CharField(widget=forms.Textarea(attrs={"rows":"5"}))
    agent_promt = forms.CharField(widget=forms.Textarea(attrs={"rows":"5"}))
    promt = forms.FileField(required=False,widget=forms.ClearableFileInput(attrs={'accept': '.xlsx'}))
    text_one_remember = forms.CharField(widget=forms.Textarea(attrs={"rows":"5"}))
    text_two_remember = forms.CharField(widget=forms.Textarea(attrs={"rows":"5"}))
    proxy_host = forms.CharField()
    proxy_port = forms.CharField()
    proxy_user = forms.CharField()
    proxy_password = forms.CharField()
    