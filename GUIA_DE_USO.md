# Guía de uso de LightManager

## 1. Primeros pasos (Estudio)

1. Selecciona el objeto que quieres iluminar y abre **LightManager › Panel de luces**.
2. En **Esquemas › Estudio**, pulsa *Aplicar* en **Tres puntos**. Aparecen la clave, el relleno y la contra mirando al
   objeto desde el lado de la cámara de render.
3. Haz un render de prueba (o abre el IPR en RenderDesk).
4. Elige una luz en la lista y ajústala en la ficha:
   - **Potencia** en pasos: `2×` dobla la luz y `½×` la reduce a la mitad.
   - **Color** en Kelvin: tirando a 3200 K es luz de bombilla; 5600 K, luz de día.
   - Arrastra su punto en la **órbita** para girarla alrededor del objeto. La rueda del ratón la sube o la baja.
5. Para colocar un brillo exacto, elige la luz, pulsa **Apuntar › Reflejo** y haz clic en el visor donde quieres el
   brillo. Esc para terminar.

## 2. Interiores y exteriores (Escena)

1. Pulsa **Escena** arriba del panel. La vista pasa a ser la escena desde arriba.
2. **Zonas ▾ › Una zona por grupo del Outliner** si tienes la casa organizada por habitaciones; si no, selecciona el
   suelo de una habitación y usa *Zona con los objetos seleccionados* (o dibuja un rectángulo en la vista).
3. Selecciona los cristales de las ventanas y pulsa **Ventanas → portales**.
4. En **Cielo**, elige el lugar, la fecha y la hora del sol. Mueve la hora para ver cómo cambia la luz.
5. Selecciona las lámparas y pulsa **Lámparas**; para downlights de techo, **Colocar ▾ › Downlight de techo** y haz clic
   en el techo. **Repetir** hace una fila de luces gemelas que cambian juntas.
6. Prueba los esquemas de **Interior** (día, atardecer, noche): ajustan el sol, el cielo y las lámparas de una vez.

## 3. Guardar y comparar

- **Escenarios › Guardar como está** guarda una foto de las luces dentro de la escena.
- Elige un escenario y **mantén pulsado Comparar** para verlo; al soltar vuelves a como estabas.
- **Esquemas › Guardar las luces como esquema** lo guarda en *Mis esquemas* para usarlo en otras escenas.

## 4. Antes de renderizar

Abre **Comprobar**. Lo rojo hay que arreglarlo (render negro, solo olvidado…); lo ámbar conviene mirarlo. Casi todo
tiene un botón que lo arregla.

## Trucos

- Las luces que crea LightManager se llaman `LM_<nombre>` y van al grupo `LM_luces`; las zonas a `LM_zonas`.
- Puedes seguir moviendo las luces con las herramientas de Maya: el panel lo recoge al volver a él.
- En el Editor de atajos (*Custom Scripts › LightManager*) puedes poner atajos a «Apuntar», «Tres puntos» o
  «Quitar todos los solos». Con Radial aparecen solas en el menú.
