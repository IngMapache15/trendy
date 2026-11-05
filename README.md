# Monitor Calendario de Adviento Trendy 2026

Revisa www.maquillajetrendyshop.com cada ~45 segundos y manda una notificación
urgente al celular cuando el calendario aparece o queda disponible para la venta.
Preventa anunciada para el martes 10 de noviembre, sin hora exacta.

## Qué revisa
1. La API pública del catálogo VTEX (busca "calendario" y "adviento"): detecta si el
   producto aparece y si tiene stock (`IsAvailable` / `AvailableQuantity`).
2. El buscador de VTEX IO, como respaldo.
3. La página principal: avisa si aparece la palabra "adviento" (banner o enlace).

Se excluye el calendario de niñas, que sale en diciembre.

## Avisos
- 👀 **Apareció el calendario**: el producto ya está publicado, pero todavía no se puede comprar.
- 🚨 **A LA VENTA**: hay stock. Llegan 5 avisos seguidos y después uno cada 10 minutos.

## Instalación (10 minutos)
1. **ntfy en el celular**: instala la app *ntfy* (Android o iPhone). Dale a "+" y
   suscríbete a un tema con un nombre difícil de adivinar, por ejemplo
   `trendy-ar-8f3k29`. Permite las notificaciones.
2. **Repo en GitHub**: crea un repositorio **público** (así los minutos de Actions
   son ilimitados). Sube `monitor.py` y la carpeta `.github/workflows/monitor.yml`.
   El nombre del tema va en un secret, así que no queda expuesto.
3. **Secret**: en el repo, ve a Settings → Secrets and variables → Actions →
   New repository secret. Ponle de nombre `NTFY_TOPIC` y de valor el nombre del tema.
   - Telegram (opcional): agrega también `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`.
4. **Prueba**: en la pestaña Actions, abre "Monitor Calendario Trendy", dale a
   Run workflow y deja marcado "Modo prueba". Te debe llegar "✅ Monitor Trendy activo".
   En el log, cada ciclo muestra lo que encontró.
5. Con eso ya queda: corre solo cada hora del 5 al 15 de noviembre.
   Cuando compres, desactívalo desde Actions → ⋯ → Disable workflow.

## Ajustes
- Para revisar más seguido, cambia `INTERVALO_SEG` en el workflow (no lo bajes de 20).
- Si el nombre del producto no dice "calendario" ni "adviento", ajusta `FILTRO_NOMBRE`
  en `monitor.py`.
