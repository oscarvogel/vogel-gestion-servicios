# Arquitectura

Multiempresa desde la primera migración. Toda entidad de negocio llevará `company_id` salvo tablas globales explícitas. La empresa activa se valida contra sesión y membresías; nunca se confía en un `company_id` libre enviado por frontend.

PortalVogel y WhatsApp se mantienen detrás de adaptadores.
