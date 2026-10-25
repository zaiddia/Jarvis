# Jarvis 5.9 — Asistente virtual para Windows

Un HUD pequeño, semitransparente y siempre visible en una esquina de la pantalla. Escucha tu voz (Vosk, sin internet), responde con IA local (Ollama) o compatible OpenAI, habla con voz neuronal (Edge-TTS) y **controla el PC**: abre y cierra aplicaciones, maneja ventanas, volumen, brillo, música, web, archivos y energía.

## Instalación

1. **Descomprime el ZIP** (clic derecho › *Extraer todo*). No ejecutes nada desde dentro del ZIP.
   **No lo pongas dentro de OneDrive** (Escritorio, Documentos o Imágenes suelen estarlo): OneDrive sincroniza los miles de archivos que se instalan y todo va muy lento. Si lo detecta, `instalar.bat` ofrece copiar Jarvis a `C:\Jarvis`.
2. Doble clic en **`instalar.bat`**. Él solo:
   - Busca un Python que funcione (prefiere 3.12; acepta 3.10 a 3.14). Si no hay ninguno, **instala Python 3.12 automáticamente** con winget.
   - Crea el entorno `.venv` (y lo rehace si quedó dañado de un intento anterior).
   - Instala los componentes **uno por uno**: si alguno falla, los demás siguen y al final te dice cuál.
   - Descarga el modelo de voz, crea los accesos directos **Jarvis** e intenta los extras opcionales (Piper, Whisper, Spotify).
3. Abre Jarvis desde el acceso directo del Escritorio (o con doble clic en `Jarvis.vbs`).
4. IA: en *Ajustes › IA* elige proveedor (Gemini, Claude, ChatGPT, DeepSeek, Kimi, Grok, Mistral, Groq u OpenRouter), pega tu clave y pulsa **Probar**. O instala **Ollama** (https://ollama.com) para IA local sin internet.

Todo lo que hace el instalador queda en **`instalar.log`** (en la misma carpeta). Si algo falla, ese archivo dice el motivo exacto.

> **Python 3.14:** PyAudio y pygame no tienen instalador para esa versión. Jarvis usa en su lugar **sounddevice** (micrófono) y **pygame-ce** (audio), que sí funcionan, así que no necesitas Visual C++ ni bajar de versión.

**No se abre ninguna consola.** Solo aparece el HUD en la esquina y un icono junto al reloj. Si algo falla, usa `depurar.bat`, que sí muestra la consola, o mira `%APPDATA%\Jarvis\jarvis.log`.

## El HUD

| Tamaño | Qué muestra |
|---|---|
| **Orbe** (92 px) | Solo el reactor, que cambia de color y pulsa según lo que hace Jarvis |
| **Compacto** | Reactor, estado, la última respuesta y una barra para escribir órdenes |
| **Expandido** | Además, la conversación completa y el registro técnico |

- **Mover:** arrastra el reactor o el título. Jarvis recuerda dónde lo dejaste.
- **Cambiar de tamaño:** doble clic en el reactor, o los botones ⤢ y ◎.
- **Ocultar:** botón —. Vuelve con **Ctrl+Alt+J** o desde el icono de la bandeja.
- **Hablar sin decir «Jarvis»:** **Ctrl+Alt+Espacio**.
- **Discreto:** fondo semitransparente regulable. Se atenúa solo cuando no lo usas y reaparece al pasar el ratón o al hablar. No ocupa sitio en la barra de tareas.
- **Icono de la bandeja:** clic derecho para mostrar u ocultar, cambiar de tamaño, pausar el micrófono, abrir Ajustes, ver el registro o salir.

## Control del PC

> **Seguridad:** las acciones destructivas (apagar, reiniciar, suspender, cerrar sesión, vaciar la papelera, forzar cierre, cerrar todo) solo se activan con la orden directa y exacta, y siempre piden confirmación. La IA nunca puede elegirlas por su cuenta aunque entienda mal una orden.

Por voz, empieza con «Jarvis» (por ejemplo, «Jarvis, abre Spotify»). Por escrito, no hace falta.

| Qué | Ejemplos |
|---|---|
| Abrir aplicaciones | «abre Spotify», «abre Word», «abre la calculadora», «abre WhatsApp». Encuentra cualquier programa del menú Inicio, también los de la Microsoft Store |
| Cerrar aplicaciones | «cierra esto» o «cierra esta ventana» (cierra la de primer plano con Alt+F4), «cierra Chrome», «cierra el explorador», «cierra Word a la fuerza» ⚠, «cierra todo» ⚠ |
| Traer al frente | «cambia a Excel», «ve a Spotify» |
| Ventanas | «minimiza todo», «maximiza esta ventana», «restaura», «cambia de ventana» |
| Carpetas y ajustes | «abre descargas», «abre documentos», «abre la configuración del wifi», «abre bluetooth» |
| Web | «abre youtube», «abre github.com», «busca recetas de arepas», «pon Despacito en YouTube» |
| Audio y música | «volumen al 30», «sube el volumen», «silencio», «pausa», «siguiente canción» |
| Pantalla | «brillo al 70» (portátiles), «toma una captura de pantalla» |
| Escribir por ti | «escribe: Hola, llego en diez minutos» (lo pega en la ventana activa), «teclea buenos días» |
| Archivos | «busca el archivo presupuesto», «abre el archivo informe final» |
| Sistema | «¿cómo está el PC?», «qué ventanas tengo abiertas», «bloquea el equipo» |
| Energía ⚠ | «apaga el equipo», «reinicia el PC», «suspende el equipo», «cierra sesión», «vacía la papelera», «cancela el apagado» |
| Presentaciones | «siguiente diapositiva», «diapositiva anterior», «inicia la presentación», «sal de la presentación», «pantalla en negro» |
| Proyector / videobeam | «activa el videobeam», «proyector en duplicar», «proyector en extender», «solo proyector» |
| Dictado | «inicia el dictado» y habla; «modo matemáticas» para fórmulas; «nueva línea»; «terminar dictado» |
| Matemáticas | «cuánto es el 15% de 240», «resuelve 2x+3=7», «deriva x cuadrado», «factoriza x cuadrado menos 4» |
| Temporizadores | «pon un temporizador de 15 minutos para el examen», «cuánto queda», «cancela el temporizador» |
| Modo sigilo | «modo sigilo» o «escóndete» oculta el panel (sigue escuchando); «mostrar panel» lo trae de vuelta |
| Talleres | «abre el taller de estadística» abre tu formulario HTML de la carpeta de Talleres |
| Otros | hora y fecha, recordatorios, documentos STEAM, numerología, reporte matutino, WhatsApp (escrito: `whatsapp +57300… mensaje`) |

⚠ = Jarvis pide confirmación antes de hacerlo. Responde «confirmar» o «cancelar». El apagado y el reinicio esperan un minuto, así que aún puedes decir «cancela el apagado».

**Órdenes libres con IA:** si una frase no coincide con ninguna orden directa, la IA la interpreta y elige la acción adecuada. Por ejemplo, «quiero escuchar algo de salsa» abre YouTube y «hay demasiada luz en la pantalla» baja el brillo. Si no es una acción, simplemente responde. Puedes desactivarlo en *Ajustes › Control del PC*.

**Atajos personalizados:** en *Ajustes › Control del PC* puedes añadir líneas como `mi proyecto = C:\Users\yo\Documents\Proyecto`. Después basta con decir «abre mi proyecto».

Por seguridad, Jarvis nunca ejecuta comandos arbitrarios: solo las acciones de la lista.

## Ajustes (botón de ajustes del HUD o icono de la bandeja)

General · **HUD** (tamaño inicial, posición, opacidad, atenuar en reposo, siempre visible, ocultar de la barra de tareas) · Voz · Escucha · IA · **Control del PC** · Rutinas · Acerca de.

Se guardan en `%APPDATA%\Jarvis\config.json` y se aplican al momento.

### Conectar la IA
- **Ollama:** `http://127.0.0.1:11434`. Pulsa *Probar y listar*.
- **LM Studio:** activa su servidor, elige *Compatible OpenAI* y usa `http://127.0.0.1:1234/v1`.

## Ejecutable

`compilar.bat` genera `dist\jarvis\jarvis.exe`, con icono y sin consola. Los accesos directos pasan a apuntar al ejecutable. Para arrancar con Windows, activa *Ajustes › General › Iniciar con Windows*.

## Modo sigilo (arrancar oculto)

Para que Jarvis trabaje sin ocupar la pantalla:

- Di «modo sigilo» (o «escóndete») y el panel desaparece, pero el micrófono sigue activo. Di «mostrar panel» o pulsa **Ctrl+Alt+J** para traerlo de vuelta.
- Para que arranque así **al encender el PC**: *Ajustes › HUD › Modo sigilo › Arrancar oculto*. Combínalo con *Ajustes › General › Iniciar con Windows*. Al iniciar no verás nada, pero Jarvis ya está escuchando.
- Como no se ve, déjalo **confirmar por voz al iniciar** (activado por defecto): dirá en voz alta que el núcleo se cargó.

## Tu propio icono

Pon un archivo `icono.ico` en la carpeta `recursos`. Jarvis lo usará en el icono de la bandeja, y `compilar.bat` lo pondrá como icono del `jarvis.exe` y de los accesos directos. Si no hay ninguno, usa el icono cian que genera solo.

## Talleres HTML del aula

1. Guarda tus formularios o actividades en HTML en la carpeta de talleres (por defecto `Documentos\Jarvis\Talleres`; puedes cambiarla en *Ajustes › Control del PC*).
2. Di «Jarvis, abre el taller de estadística» y se abre en el navegador.
3. Para **rellenarlo por voz**: haz clic en el primer campo y di «inicia el dictado». Dicta los valores y usa estos comandos para moverte y operar los controles:

| Dices | Hace |
|---|---|
| «siguiente campo» / «campo anterior» | Salta al siguiente control (Tab) o al anterior |
| «modo matemáticas» … «modo normal» | Dicta fórmulas («dos equis más tres igual siete» → `2x+3=7`) |
| «marca» / «desmarca» / «marca la casilla» | Activa o quita una casilla o botón de opción |
| «elige Grado once» / «selecciona azul» / «pon verde» | Escoge esa opción de una lista desplegable |
| «abre la lista» / «despliega» … «cierra la lista» | Abre o cierra un menú desplegable |
| «abajo» / «arriba» / «siguiente opción» / «opción anterior» | Mueve entre opciones de una lista o botones de opción |
| «derecha» / «izquierda» | Mueve un deslizador o control horizontal |
| «borra el campo» / «borrar» | Limpia el campo o borra lo último |
| «enviar» / «aceptar» | Envía el formulario (Enter) |
| «terminar dictado» | Sale del dictado |

## Modo dictado y aula

Para escribir con la voz en cualquier programa (Word, el navegador, un formulario…):

1. Abre el documento y deja el cursor donde quieras escribir.
2. Di «Jarvis, inicia el dictado». A partir de ahí, todo lo que digas se escribe, sin repetir «Jarvis».
3. Di «modo matemáticas» para dictar fórmulas: «dos equis más tres igual a siete» escribe `2x+3=7`. Vuelve con «modo normal».
4. «nueva línea» hace un salto de línea; «borrar» borra lo último.
5. Di «terminar dictado» para volver al modo normal.

Para dar clase con proyector: di «activa el videobeam» (lo duplica), controla las diapositivas con «siguiente diapositiva» / «diapositiva anterior», e «inicia la presentación» para ponerla a pantalla completa.

Jarvis también **recuerda la conversación entre sesiones** (en `memoria.json`). Di «nueva conversación» o usa el botón *Nueva* del HUD para empezar de cero.

## Llevar Jarvis en una USB

1. Copia en la carpeta `recursos` lo que quieras llevar, por ejemplo `sirena.mp3`.
2. Si usas una clave de API u otra configuración fija, copia `.env.ejemplo` como `.env` y rellénalo.
3. Ejecuta **`compilar_usb.bat`**. Al terminar, copia la carpeta `USB\Jarvis` completa a tu memoria.
4. En cualquier PC con Windows 10 u 11, abre `Jarvis\jarvis.exe`. No necesita instalar nada.

En la USB, Jarvis funciona en **modo portable**:
- Los ajustes, el registro, los documentos y las capturas se guardan en la propia memoria (`datos` y `Documentos Jarvis`).
- No modifica el inicio de Windows del equipo donde lo uses.
- Ya incluye el modelo de voz, la interfaz, tus recursos y el `.env`, sin pasos manuales.
- La IA necesita Ollama en ese equipo, o en otro de la red (`OLLAMA_HOST` en el `.env`), o un servicio compatible OpenAI.

## Archivo .env

Si existe un `.env` junto a `jarvis.py` o `jarvis.exe`, sus valores mandan sobre los Ajustes y nunca se escriben en `config.json`. Sirve para claves de API o para fijar la configuración de la USB. Mira `.env.ejemplo`.

## Sonido de alarma

Pon `sirena.mp3` en `recursos` (o elige otro archivo en *Ajustes › Rutinas*). Sonará antes de que Jarvis lea cada recordatorio, también con la voz desactivada.

## Copias de seguridad (v5.9)

En *Ajustes › Acerca de › Copias de seguridad* (o diciendo **«Jarvis, haz una copia de seguridad»**)
Jarvis guarda en un solo archivo .zip:
- tus **ajustes** (voz, personalidad, palabra de activación, proveedor de IA…),
- tus **notas y recordatorios**,
- tus **cursos, listas y asistencia**,
- tus **rutinas** y la **memoria** de la conversación.

Las copias quedan en `Documentos\Jarvis\Respaldos` (puedes elegir otra carpeta, por ejemplo una
de OneDrive para tenerlas también en la nube). Cada semana se hace una **automática** y se guardan
las 8 últimas; las que haces tú nunca se borran solas.

**Restaurar:** pulsa *Restaurar…* en una copia de la lista (o *Restaurar desde un archivo…* si la
traes en una USB o por correo), elige qué partes quieres recuperar y confirma. Antes de reemplazar
nada, Jarvis guarda una copia de cómo estaba todo, por si te arrepientes. No hace falta reiniciar.

**Pasar Jarvis a otro computador:** instala Jarvis allá, abre *Ajustes › Acerca de* y restaura la
copia. El micrófono y las carpetas se dejan como están en el equipo nuevo.

**Claves de API:** por defecto **no** se guardan en la copia, para que puedas llevarla en una USB
sin riesgo; al restaurarla en otro equipo vuelves a pegar las claves en *Ajustes › IA*. Si activas
«Incluir mis claves de API», quien tenga el archivo tiene tus claves: no lo compartas.
Restaurar solo se hace desde Ajustes (por voz únicamente se crean copias).

## Sin internet y actualizaciones (v5.8)

**Si se cae el internet, Jarvis sigue.** Lo nota solo (en menos de un minuto) y pasa a lo que hay en
tu equipo; te lo dice en voz alta y en el HUD aparece un rombo naranja junto a los indicadores.
- **IA:** responde con **Ollama** (la IA local). Si una pregunta se corta a mitad porque se fue la
  conexión, la repite en local sin que tengas que volver a preguntar.
- **Voz:** usa **Piper**. **Escucha:** solo el reconocimiento del equipo (Vosk o Whisper).
- Cuando vuelve el internet, regresa a Gemini (o al proveedor que uses) y te avisa.
- Sin una IA local instalada, siguen funcionando todas las órdenes del PC, temporizadores, notas,
  rutinas y el tablero; solo las preguntas abiertas necesitan internet.
- Para tenerlo listo, una sola vez con internet: instala Ollama (ollama.com), ejecuta
  `ollama pull llama3.2` y `python descargar_voz.py`. En *Ajustes › IA › Si se cae el internet*
  ves si quedó todo listo y puedes elegir el modelo.

**Actualizar con un botón.** En *Ajustes › Acerca de › Actualizaciones*:
1. Escribe el repositorio de GitHub donde publicas Jarvis (`usuario/jarvis`) y guarda.
2. **Buscar actualización** → si hay una más nueva, verás sus novedades y el botón **Actualizar**.
3. Jarvis descarga el .zip, guarda una **copia de seguridad** de lo que reemplaza, instala los
   componentes nuevos si hacen falta y se reinicia solo.
4. ¿Algo salió mal? **Deshacer la última actualización** lo deja como estaba.

Nunca toca tus ajustes, notas, cursos ni rutinas (están en `%APPDATA%\Jarvis`), ni tu `.env`,
tu icono, el modelo de voz o las voces de Piper. Una vez al día mira si hay versión nueva y solo
lo avisa: nunca se instala ni se reinicia sola (así no pasa en mitad de una clase). Por voz:
«Jarvis, ¿hay actualizaciones?» o «¿qué versión eres?».

**Publicar una versión** (quien mantiene Jarvis):
1. Sube el número en `VERSION = "…"` de `jarvis.py`.
2. Ejecuta `python empaquetar_version.py`: crea `publicar\jarvis_project_vX.Y.zip` **sin tus
   claves** (.env), sin .venv, sin el modelo de voz ni el .exe.
3. En GitHub: *Releases › Draft a new release*, etiqueta `vX.Y`, adjunta ese .zip y publica.
Si el repositorio es privado, cada equipo necesita una clave de GitHub de solo lectura
(*fine-grained token* con permiso *Contents: Read*) en el campo «Clave de GitHub».

## Voz de Gemini e interrumpirlo (v5.7)

**Voz muy natural.** En *Ajustes › Voz* elige **Gemini (muy natural)**. Usa la misma clave de Gemini
que ya tienes en *Ajustes › IA*. Puedes elegir entre 30 voces (Charon, Kore, Sulafat, Puck…), la
calidad (rápida o máxima) y describir con tus palabras cómo quieres que hable: «cálido y tranquilo»,
«enérgico», «pausado, como un profesor». Pulsa **Probar voz** para oírla antes de guardar.

- Mientras dice una frase, Jarvis ya está preparando la siguiente: no hay silencios entre frases.
- Si Gemini falla (sin cuota, sin saldo, clave mala), esa frase sale con **Edge** y Gemini queda en
  pausa 15 minutos; lo verás una sola vez en el Registro. Sin internet, usa **Piper**.
- Las frases cortas que se repiten («¿Sí?», «Hecho») se guardan en tu equipo (carpeta `voz_cache`)
  para que suenen al instante y no gasten cuota.
- La velocidad, el volumen y el tono de los deslizadores solo aplican a Edge y Piper; en Gemini el
  ritmo se describe en «Forma de hablar».

**Interrumpirlo.** Mientras Jarvis habla puedes decir:
- **«Jarvis, para»**, «Jarvis, cállate», o solo «basta» / «cállate» → se calla al momento.
- **«Jarvis, …» con otra pregunta** → deja lo que estaba diciendo y te responde lo nuevo.

Jarvis ignora su propia voz si la oye por los parlantes y la conversación del salón (solo atiende si
lo llamas por su nombre). Si se corta solo, baja el volumen de los parlantes, usa audífonos o
desactiva *Ajustes › Escucha › Interrumpirlo mientras habla*.

## Rutinas con nombre (v5.5)

Una frase lanza varias órdenes seguidas. Vienen tres de ejemplo, que puedes cambiar en *Ajustes › Rutinas*:

| Di | Hace |
|---|---|
| «modo clase» / «empecemos la clase» | activa el videobeam, volumen al 40, silencia las notificaciones, abre el tablero |
| «fin de clase» | pone el videobeam en solo PC, activa las notificaciones, volumen al 30 |
| «modo planeación» | silencia las notificaciones, abre Word y la carpeta Documentos |

**Crear las tuyas:** un nombre, las frases que la lanzan y **una orden por línea**: las mismas frases que le dirías a Jarvis («usa el curso 7A», «abre powerpoint», «pon un temporizador de 45 minutos para el examen», «activa el semáforo de ruido»…). Además puedes usar `esperar 5` (pausa) y `decir …` (lo dice en voz alta).

- Durante la rutina, cada paso se anota en el HUD sin hablar; solo se oyen los «decir» y el aviso final.
- Por seguridad, una rutina **nunca** ejecuta acciones delicadas (apagar, reiniciar, cerrar todo, vaciar la papelera…) ni otras rutinas: se las salta y te lo dice.
- «¿Qué rutinas tengo?» las enumera.

**Notificaciones:** también puedes decir «silencia las notificaciones» / «activa las notificaciones» (o «no molestar») en cualquier momento. Es el mismo ajuste de *Configuración › Sistema › Notificaciones* de Windows.

## Calendario de Google u Outlook (v5.6)

Jarvis lee tu calendario (solo lectura) y lo junta con tus notas:

- «¿qué tengo hoy?», «¿qué tengo mañana?», «¿qué tengo esta semana?»: eventos y notas, ordenados por hora.
- «¿cuál es mi próxima clase?», «¿mi próxima reunión?», «¿qué sigue?».
- Te avisa **10 minutos antes** de cada evento (ajustable).
- Al abrir Jarvis, el HUD muestra lo de hoy, y la IA lo conoce para preguntas libres («¿a qué hora es la izada?»).
- «Actualiza el calendario» lo relee al momento (también se actualiza solo cada 10 minutos).

**Conectarlo** (*Ajustes › Memoria › Calendario*):
- **Google Calendar:** en calendar.google.com, pasa el ratón sobre tu calendario › ⋮ › *Configuración y uso compartido* › *Dirección secreta en formato iCal*. Cópiala, pégala en Jarvis, pulsa *Probar* y luego *Guardar*.
- **Outlook:** ⚙ › *Calendario* › *Calendarios compartidos* › *Publicar un calendario*, elige «Puede ver todos los detalles» y copia el enlace ICS.

Puedes poner varios calendarios, uno por línea (por ejemplo, el personal y el del colegio). Ese enlace es **secreto**: quien lo tenga puede ver tus eventos. Jarvis lo guarda solo en tu equipo y nunca lo muestra en pantalla. Para crear eventos por voz haría falta otra conexión, más compleja, con tu cuenta de Google; por ahora, para apuntar cosas usa la memoria («recuerda que…»).

## Memoria personal (v5.3)

Jarvis recuerda lo que le pidas, con fecha y hora si las dices:

| Para… | Di |
|---|---|
| Anotar | «recuerda que la reunión de padres es el jueves a las 3», «anota que debo comprar marcadores», «toma nota de que el 15 de noviembre es la izada de bandera» |
| Consultar | «¿qué tengo pendiente?», «¿qué tengo hoy?», «¿qué tengo mañana?», «¿qué tengo esta semana?» |
| Tachar | «ya compré los marcadores», «ya hice lo de la reunión», «tacha lo de las planillas» |
| Borrar | «borra la nota de la izada», «borra las notas hechas» |

**Fechas que entiende:** hoy, mañana, pasado mañana, el jueves, el próximo lunes, el 15 de noviembre, 15/11, a las 3, a las 3 y media, a las 10:30 de la mañana, al mediodía. «A las 3», sin más, se toma como de la tarde.

**Avisos:** si la nota tiene hora, Jarvis avisa 30 minutos antes (ajustable) y otra vez a la hora, con el sonido de alarma. Al abrir Jarvis verás en el HUD los pendientes de hoy, y el reporte matutino también los dice.

**Preguntas libres:** la IA conoce tus pendientes, así que puedes preguntar «¿a qué hora era lo de los padres?». Puedes apagarlo en *Ajustes › Memoria*, donde también ves, añades, tachas y borras notas a mano.

«Recuérdame **en** 10 minutos…» sigue siendo la alarma de siempre; «recuérdame **que el jueves**…» es una nota. Todo se guarda solo en tu equipo (`notas.json`).

## Revisar trabajos (v5.4)

Muéstrale a Jarvis un taller, examen o cuaderno y te dice aciertos, errores con su corrección, una **nota sugerida (1,0 a 5,0)** y un mensaje para el estudiante.

- **Por voz:** «revisa el taller de Juan», «califica este examen», «corrige la tarea de Sofía». Jarvis te pide poner la hoja frente a la cámara y toma la foto a los 3 segundos. Si el trabajo está abierto en el computador: «revisa el taller de Juan **en la pantalla**».
- **En el tablero** (pestaña *Revisar*): *Cámara*, *Pantalla* o *Subir foto* (por ejemplo, una foto tomada con el celular). Eliges al estudiante y, si quieres, escribes las **respuestas correctas o criterios**, que mejoran mucho la revisión. Luego pulsas *Revisar con IA*.
- **Se guarda:** un Word en *Documentos Jarvis › Revisiones* con la foto, la nota, las correcciones y el mensaje, y una fila en *Registro de revisiones.csv* (abre en Excel), útil como planilla de notas.

**Consejos:** buena luz, la hoja derecha y llenando la imagen. La letra muy pequeña se lee mejor con una foto del celular que con la cámara del portátil. Si la imagen no se lee bien, Jarvis lo dice en vez de inventar.

**Importante:** la nota es **una sugerencia**; la decisión final es tuya. Las imágenes de los trabajos se envían a tu proveedor de IA (Gemini, Claude o ChatGPT). Con Ollama se quedan en tu equipo, aunque su revisión es más simple. Para usar la cámara hace falta el componente OpenCV: si ya tenías Jarvis instalado, ejecuta `instalar.bat` una vez más.

## Herramientas de aula (v5.2)

Abre el **tablero del aula** diciendo «Jarvis, abre el tablero», o desde el icono junto al reloj › *Tablero del aula*. Arrástralo al videobeam y ponlo en pantalla completa con el botón de la esquina o con F11.

**1. Crea tus cursos** (pestaña *Cursos*): ponle nombre (7A, 8B…) y pega la lista de estudiantes, un nombre por línea. Puedes copiar la columna de nombres directamente desde Excel: Jarvis quita numeraciones y columnas sobrantes.

| Qué | Por voz | En el tablero |
|---|---|---|
| Cambiar de curso | «usa el curso 7A», «cambia al grado séptimo A» | Selector *Curso* |
| Sortear un estudiante | «escoge un estudiante», «¿quién pasa al tablero?», «otro» | *Ruleta* › Sortear (o barra espaciadora) |
| Nueva ronda | «reinicia la ruleta» | *Nueva ronda* |
| Grupos | «haz grupos de 4», «forma 5 grupos», «haz parejas» | *Grupos* |
| Asistencia | «llama a lista», «falta Juan», «faltan Sofía y Carlos», «llegó Juan», «guarda la asistencia» | *Asistencia*: toca a quien falte |
| Semáforo de ruido | «activa el semáforo de ruido» | *Semáforo* |

- **Sorteo justo:** nadie repite hasta que hayan pasado todos, y se salta a quien faltó hoy.
- **Grupos equilibrados:** sin los ausentes del día; los tamaños difieren como mucho en 1.
- **Asistencia:** se guarda en *Documentos Jarvis › Asistencia* como un archivo que abre Excel (una fila por estudiante, con Presente/Ausente).
- **Semáforo de ruido:** usa el micrófono de Jarvis (no graba nada). Verde está bien, amarillo es un aviso y rojo pide silencio. La *Tolerancia* ajusta lo exigente que es según tu salón.

**2. Material de clase en Word.** Dilo así:
- «crea un quiz de 10 preguntas sobre fracciones para séptimo»
- «hazme un taller de ecuaciones para grado 8»
- «prepara una rúbrica para exposiciones orales»
- «haz un plan de clase sobre el ciclo del agua»

También puedes usar la pestaña *Material*. Jarvis lo redacta con tu IA y lo guarda en *Documentos Jarvis › Material de clase*, con el encabezado de tu institución, tu nombre como docente y una línea para el nombre del estudiante. Las evaluaciones y talleres incluyen al final la **clave de respuestas** para ti. Las rúbricas usan la escala **Superior, Alto, Básico y Bajo** y salen en horizontal. Tus datos para el encabezado se ponen una vez en la pestaña *Material*.

La IA puede equivocarse: **revisa siempre el material antes de usarlo en clase**.

## Ayuda con lo que tienes en pantalla (v5.1)

**A demanda.** Di, por ejemplo:
- «Jarvis, ayúdame con esto» o «¿qué me sugieres?»
- «revisa lo que estoy haciendo» o «¿cómo mejoro esto?»

Jarvis captura la pantalla (ocultando el HUD un instante), ve en qué estás trabajando y te da dos o tres sugerencias concretas en voz alta. Recuerda lo que vio, así que puedes seguir con «¿y cómo hago eso?». «¿Qué hay en la pantalla?» sigue funcionando para una simple descripción.

**Copiloto.** Di «activa el copiloto» (o «copiloto cada 10 minutos»), o actívalo en *Ajustes › IA › Copiloto de pantalla*. Mientras trabajas mira tu pantalla cada pocos minutos y, **solo si tiene algo útil**, te deja una sugerencia en el HUD; puedes pedir que también la diga en voz alta. Mientras está activo, el HUD muestra un **punto naranja**. «Desactiva el copiloto» lo para.

En *¿En qué trabajas?* puedes contarle tu contexto (por ejemplo, «soy docente de matemáticas») y las sugerencias serán mucho más útiles.

**Cuidados incluidos:**
- No mira si estás ausente (más de 2 minutos sin tocar teclado ni ratón) ni si la pantalla no cambió.
- **Nunca captura ventanas privadas**: contraseñas, inicio de sesión, bancos, pagos o navegación privada.
- No repite sugerencias.
- Las capturas se reducen a 1280 px para gastar menos cuota.

**A tener en cuenta:** las capturas se envían a tu proveedor de IA (Gemini, Claude o ChatGPT; con Ollama se quedan en tu equipo). Si tu IA no ve imágenes, por ejemplo DeepSeek, se usa tu clave de Gemini. Cada mirada del copiloto es una consulta, así que con la cuota gratuita conviene un intervalo de 5 minutos o más.

## Que Jarvis te entienda bien (v5.0): escucha en dos etapas

Si Jarvis responde cosas raras, casi siempre es porque **oyó mal**, no porque la IA piense mal. Mira el *Registro* del HUD: ahí aparece lo que entendió.

Desde la v5.0 la escucha funciona en dos etapas:

1. **Vosk escucha siempre en tu equipo**, gratis y sin enviar nada, pero solo para saber si le estás hablando a Jarvis.
2. **Si la frase es para Jarvis**, ese mismo audio se transcribe con un reconocedor preciso: **Gemini** (con tu clave) o **Whisper** (en tu equipo). Se le pasan las palabras que suelen aparecer: tus contactos, las aplicaciones y las órdenes de Jarvis.

Lo que se habla en el ambiente **nunca sale de tu PC**. Se configura en *Ajustes › Escucha › Entender mejor lo que le dices* (por defecto, automático). En el *Registro* verás líneas como `Entendido con Gemini en 0.9 s (el reconocimiento local había oído: «…»)`.

Además, Jarvis reconoce su nombre aunque llegue deformado («yarvis», «jarvi») o con una muletilla delante («hola Jarvis», «ya Jarvis»), y la IA sabe que el texto viene de la voz y puede traer errores.

**Consejos que también ayudan:** micrófono a menos de un metro, *Sensibilidad* en 0 (*Ajustes › Escucha*), y decir «Jarvis» y la orden seguidos, sin pausa larga.

## Proveedores de IA (v4.9)

En *Ajustes › IA › Proveedor de IA* eliges con qué IA habla Jarvis. Cada proveedor guarda su propia clave y su propio modelo, así que puedes cambiar de uno a otro sin volver a pegar nada.

| Proveedor | Dónde se saca la clave | Modelo recomendado | Ve la pantalla |
|---|---|---|---|
| **Ollama** (en tu equipo) | No necesita | `llama3.2` | Sí, con `moondream` |
| **Google Gemini** | aistudio.google.com/apikey | `gemini-3.5-flash-lite` | Sí |
| **Claude** (Anthropic) | console.anthropic.com | `claude-haiku-5-5` | Sí |
| **ChatGPT** (OpenAI) | platform.openai.com/api-keys | se elige solo | Sí |
| **DeepSeek** | platform.deepseek.com | `deepseek-flash` | No |
| **Kimi** (Moonshot AI) | platform.moonshot.ai | `kimi-k3` | No |
| **Grok** (xAI) | console.x.ai | se elige solo | No |
| **Mistral AI** | console.mistral.ai | `mistral-small-latest` | No |
| **Groq** | console.groq.com | se elige solo | No |
| **OpenRouter** | openrouter.ai/keys | `openrouter/auto` | No |
| **Personalizado** | la de tu servicio | el que pongas | No |

Pasos: elige el proveedor, pega la clave, pulsa **Probar** y luego **Guardar**. El enlace de cada proveedor abre directamente su página de claves.

**«Probar» hace una prueba real:** no solo abre la lista de modelos, también pide una respuesta. Si la clave abre la lista pero el modelo no contesta, lo dice y elige otro que sí funcione.

**Si algo falla, Jarvis dice el motivo real** en voz alta y en el registro: clave inválida, sin saldo, cuota agotada, modelo no disponible, región no admitida o sin internet.

**Modelos que dejan de existir:** si el modelo elegido ya no está disponible para tu cuenta, Jarvis cambia solo al mejor disponible, lo guarda y lo anota en el registro. Es lo que pasaba con `gemini-2.5-flash`: Google ya no lo da a claves nuevas, así que la lista abría pero cada pregunta fallaba.

Ten en cuenta: los proveedores de la nube **necesitan internet**, y lo que dices (y la pantalla, cuando lo pides) se envía a esa empresa. Para privacidad total, usa Ollama.

## Integraciones nuevas (v4.3)

En *Ajustes › Integraciones*:

- **Visión de pantalla.** Di «¿qué hay en la pantalla?», «describe la pantalla» o «qué ves». Jarvis toma una captura y te la describe con un modelo de visión local. Descárgalo una vez: `ollama pull moondream` (ligero) o `ollama pull llava` (más detallado), y ponlo en Ajustes.
- **Música en Spotify.** «Reproduce Despacito en Spotify», «pausa Spotify», «siguiente en Spotify». Sin configurar, abre la búsqueda; si pones tus credenciales de Spotify (developer.spotify.com, con Premium), reproduce la canción automáticamente.
- **WhatsApp por voz.** Guarda contactos (`Nombre = +57300…`) y di «manda un whatsapp a Juan que llego tarde». Necesita WhatsApp Web con la sesión iniciada.
- **Telegram.** Con un bot de `@BotFather`, di «manda un telegram diciendo…».

Con tu portátil (16 GB, gráfica integrada) la IA corre en CPU. Recomendado: **qwen2.5:7b** para conversar y **moondream** para visión (rápidos y livianos).

## Conversación más natural

Para que Jarvis hable más natural (menos «robot»), dos cosas ayudan:

1. **Un modelo de IA más grande.** `llama3.2` (3B) es rápido pero básico. Si tu PC lo aguanta, prueba uno más capaz y notarás un salto grande en naturalidad:
   - `ollama pull llama3.1:8b`  (muy buen equilibrio, ~8 GB de RAM)
   - `ollama pull qwen2.5:7b`  (excelente en español)
   - `ollama pull gemma2:9b`  (muy natural, algo más pesado)

   Luego ponlo en *Ajustes › IA › Modelo*.
2. **La personalidad.** Jarvis ya trae una personalidad cálida y conversacional por defecto. Puedes ajustarla a tu gusto en *Ajustes › IA › Personalidad*.

Nota: un asistente en la nube (como los de Google Gemini) siempre sonará más natural que uno local pequeño, porque usa un modelo enorme. Con un modelo de 7-8B te acercas bastante, manteniendo todo **en tu equipo y gratis**.

## Más control del PC

- **Abrir/cerrar apps, ventanas:** «abre Word», «cierra esto», «cambia a Spotify», «minimiza todo», «maximiza esta ventana», **«pantalla completa»**.
- **Leer en voz alta:** selecciona un texto en cualquier programa y di **«lee esto»**; Jarvis lo lee frase por frase. Útil para leerle a la clase o revisar un documento.

## Novedades de la versión 4.0

**Voz sin internet (Piper).** En *Ajustes › Voz › Motor de voz* puedes elegir **Piper (offline)**: Jarvis habla aunque no haya conexión. La primera vez descarga una voz con `descargar_voz.py` (ver abajo) y queda guardada para siempre. Deja **Edge (online)** si prefieres sus voces y tienes internet.

**Reconocimiento más preciso (Whisper).** En *Ajustes › Escucha › Motor de reconocimiento* puedes cambiar de **Vosk** (ligero, instantáneo) a **Whisper** (bastante más preciso con acentos y ruido, pero usa más memoria). Los dos funcionan sin internet. Whisper descarga su modelo la primera vez.

**Matemáticas al instante (sin IA).** «Jarvis, cuánto es el 15 por ciento de 240», «resuelve dos equis más tres igual a siete», «deriva x al cuadrado», «factoriza x al cuadrado menos 4». Resultados exactos, al momento.

**Temporizadores de clase.** «Jarvis, pon un temporizador de 15 minutos para el examen». Aparece una cuenta regresiva en el HUD y, al terminar, suena la sirena y Jarvis avisa. Puedes tener varios: «cuánto queda», «cancela el temporizador de lectura», «cancela todos los temporizadores».

### Instalar los motores offline

`instalar.bat` ya intenta instalar Piper y Whisper. Para la voz de Piper, descarga una voz una vez (con internet):

```
.venv\Scripts\python descargar_voz.py        (España)
.venv\Scripts\python descargar_voz.py mx     (México)
.venv\Scripts\python descargar_voz.py --lista
```

Si no instalas estos extras, Jarvis sigue funcionando con Edge (voz) y Vosk (reconocimiento).

## Que no escuche el ambiente

Jarvis ya exige decir «Jarvis» antes de cada orden, así que ignora las conversaciones de fondo. Si quieres reforzarlo (aulas, oficinas), en *Ajustes › Escucha*:

- **Sensibilidad del micrófono:** súbela para que ignore los sonidos lejanos o flojos (otras personas en el salón, el pasillo). Si Jarvis empieza a no oírte a ti, bájala un poco. En 0 no filtra nada.
- **Palabra de activación** (ya activa): Jarvis solo actúa si la frase empieza por «Jarvis». Déjala encendida.
- **Solo escuchar al pulsar un atajo:** el micrófono queda en silencio total hasta que pulsas Ctrl+Alt+Espacio; entonces escucha tu siguiente frase y vuelve a callarse. Es la garantía más fuerte contra el ambiente, ideal si trabajas rodeado de gente.

Además, Jarvis descarta las transcripciones demasiado cortas (ruidos o sílabas sueltas) y nunca se escucha a sí mismo mientras habla.

Recuerda: el reconocimiento de voz (Vosk) es **local**; el audio no sale de tu equipo.

## Notas

- El HUD usa el motor de Edge (WebView2), que ya viene en Windows 10 y 11.
- **Edge-TTS necesita internet:** el texto de las respuestas se envía al servicio de voz de Microsoft. El reconocimiento de voz y la IA local no salen de tu equipo.
- Mientras Jarvis habla, ignora el micrófono para no escucharse a sí mismo.
- Si «Jarvis» no reacciona a tu voz, mira en *Registro* (HUD expandido) cómo lo transcribe Vosk y añade esa palabra en *Ajustes › Escucha*.
