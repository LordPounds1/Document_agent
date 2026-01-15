"""Agents - упрощённые агенты для работы с разными источниками документов."""

from agents.email_agent import EmailAgent
from agents.whatsapp_agent import WhatsAppAgent, WhatsAppMessage, WhatsAppChat

__all__ = ['EmailAgent', 'WhatsAppAgent', 'WhatsAppMessage', 'WhatsAppChat']
