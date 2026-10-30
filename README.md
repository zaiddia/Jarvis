# Jarvis 7.8 — Asistente virtual para Windows

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

**Descargarlo ya hecho:** en cada versión, en GitHub › Releases, está **`Ejecutable-Windows-vX.Y.zip`**: descomprímelo
(por ejemplo en `C:\Jarvis`) y abre `jarvis.exe`. No necesitas instalar Python; ya trae el modelo de voz. Tus ajustes,
notas y memoria se guardan aparte (en `%APPDATA%\Jarvis`), así que puedes cambiar entre el .exe y la versión de Python
sin perder nada. Para pasar a una versión nueva del .exe, descarga el zip nuevo y reemplaza la carpeta.

**Hacerlo tú:** `compilar.bat` genera `dist\jarvis\jarvis.exe`, con icono y sin consola. Los accesos directos pasan a apuntar al ejecutable. Para arrancar con Windows, activa *Ajustes › General › Iniciar con Windows*.

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

## Arreglo del control del navegador (v7.9.1)

«Cambia de pestaña», «cierra la pestaña», «baja», «busca en la página…», «escribe…» y «cierra esta ventana» volvían a
fallar si le dabas la orden desde el reactor de la barra de tareas: Jarvis tomaba el cuadro de órdenes del reactor
(o un menú, o Alt+Tab) como «la ventana activa» y mandaba ahí las teclas. Ahora ignora sus propias ventanas, los menús
y las vistas del sistema, y siempre actúa sobre tu navegador o la última aplicación que usaste. Si esa ventana se
cerró, usa la que esté más arriba en vez de decir «No sé sobre qué ventana actuar».

## Jarvis en todas partes: notas de voz, WhatsApp, celular instalable, imágenes y varios equipos (v7.9)

**Notas de voz por Telegram.** Mándale una nota de voz al bot: Jarvis la transcribe (con tu clave de Gemini, o con
Whisper si lo tienes), te muestra lo que entendió, la atiende como cualquier orden y te contesta también con un audio
(se apaga en *Ajustes › Integraciones*).

**Avisos al WhatsApp.** Recordatorios, avisos, tareas programadas y aprobaciones pendientes también te llegan al
WhatsApp con CallMeBot (gratis). Los pasos están en *Ajustes › Integraciones › WhatsApp*, con un botón para probar.
WhatsApp sirve para recibir avisos; para darle órdenes desde el celular usa Telegram o el panel.

**Panel del celular instalable.** Abre el panel del celular en Chrome y elige «Añadir a la pantalla de inicio»: queda
como una app, con el icono de Jarvis y a pantalla completa.

**Imágenes para tus clases.** «**Hazme una ilustración del ciclo del agua**», «**genera una imagen de una célula
animal para sexto**». Usa el modelo de imágenes de Gemini de tu cuenta y las guarda en `Documentos\Jarvis\Imágenes`.
Los proyectos también pueden incluir imágenes («…con investigación, taller e imágenes»). Si te escribe por Telegram,
te manda la imagen ahí.

**Varios equipos.** En *Ajustes › Agente › Varios equipos* pon una carpeta que se sincronice sola (OneDrive, Google
Drive para escritorio, Dropbox) en el PC del colegio y en el de la casa. Cada 3 minutos Jarvis guarda ahí tu perfil,
rutinas, tareas, notas, aula, banco de preguntas, notas de estudiantes, costumbres y habilidades, y trae lo más nuevo
del otro equipo. Tus claves, ajustes e historial no se copian.

## Aula conectada (Classroom, seguimiento, banco de preguntas) y memoria editable (v7.8)

**Google Classroom.** «**¿Qué tareas tengo en Classroom de 7A?**», «**¿quién no ha entregado el taller de fracciones en
Classroom de 7A?**», «**publica en Classroom de 7A que mañana hay examen**» (con tu aprobación) y «**trae las notas de
Classroom de 7A**» (pasa las notas a la escala de 1,0 a 5,0). Se conecta una vez en *Ajustes › Memoria › Google
Classroom*, con un ID de cliente «App de escritorio» de Google Cloud (los pasos están ahí); Jarvis guarda solo el
permiso, nunca tu contraseña.

**Seguimiento por estudiante.** «**Ponle 4,5 a Juan Pérez en el quiz de fracciones de 7A**», «**¿cómo va Juan en
7A?**» (promedio, última nota y fallas de la asistencia), «**¿quiénes están en riesgo en 7A?**» (promedio menor a 3,0
o 3 fallas o más; se ajusta). Los viernes por la tarde te avisa quién está en riesgo en cada curso.

**Banco de preguntas.** Cada quiz que Jarvis prepara guarda sus preguntas (sin repetir). «**¿Cuántas preguntas tengo
de fracciones?**», «**haz un quiz de 10 preguntas de fracciones con el banco**»: lo arma al instante y sin usar la IA,
usando primero las preguntas que menos has usado.

**Planes alineados con los DBA.** Los planes de clase (también los de los proyectos) se alinean con los Derechos
Básicos de Aprendizaje y los Estándares Básicos de Competencias del MEN, sin inventar números de DBA.

**Memoria visible y editable.** En *Ajustes › Memoria*: toca un dato de «Lo que Jarvis ha aprendido de ti» para
corregirlo o añade uno nuevo; busca en el historial de conversaciones y borra líneas sueltas; mira lo que ha
aprendido de tus costumbres y vuelve a permitir lo que rechazaste. Y Jarvis **recuerda solo**: si preguntas algo de lo
que ya le habías hablado, la IA lo tiene en cuenta («la última vez dijiste que el examen de 7A vale 30 %»).

## Galería de conectores, tu correo, tu calendario y tu casa (v7.7)

**Galería de conectores.** En *Ajustes › Integraciones › Galería de conectores* conectas tus apps con un formulario,
sin escribir JSON: **Home Assistant** (tu casa: luces, enchufes, clima, escenas y automatizaciones, con el conector
ha-mcp de unas 90 herramientas; ahora se aceptan direcciones http de tu red, como `homeassistant.local`), **GitHub**,
**Notion**, **Todoist**, **hora en el mundo** y **leer páginas web**. Te dice si a un conector le falta Node.js o uv.
Gracias a la elección por significado de la 7.5, la IA solo ve las herramientas que tienen que ver con lo que pides.

**Los conectores ahora pasan por el centro de aprobaciones.** Lo que no marques como de confianza («apaga las luces
de la sala» con Home Assistant, crear una página en Notion…) se aprueba por voz, en el HUD, el reactor, el celular o
Telegram.

**Tu bandeja de correo.** «**¿Qué correos importantes tengo?**» (resume quién escribió y qué pide, sin publicidad ni
avisos automáticos, y con tu agenda de correos primero), «**lee el correo de la coordinadora**», «**contéstale que sí
asisto**»: redacta la respuesta en el mismo hilo y **solo la envía si la apruebas**. Usa la misma contraseña de
aplicación con la que Jarvis ya envía correos, por IMAP y en modo solo lectura (no borra, no mueve ni marca nada como
leído). Botón «Probar la bandeja» en *Ajustes › Integraciones › Correo*.

**Crear eventos.** «**Agenda una reunión con los padres de Juan el jueves a las 3**», «ponme en el calendario el
consejo académico el lunes a las 7»: la IA entiende la fecha, te lo confirma y, al aprobar, abre **Google Calendar**
con el evento escrito (solo pulsas «Guardar») o crea un archivo para **Outlook / Calendario de Windows** con aviso 30
minutos antes. Se elige en *Ajustes › Memoria › Calendario*.

## Proyectos con sub-agentes y centro de aprobaciones (v7.6)

**Proyectos de varios pasos.** «**Prepárame la semana de 7A sobre fracciones**», «organiza la unidad de ecosistemas
para sexto», «hazme un proyecto: semana de la ciencia con investigación, 3 clases, taller, quiz y carta a los padres».
La IA lo convierte en un plan con pasos de tipos conocidos (investigar, plan de clase, taller, quiz, rúbrica,
presentación, textos) y sus dependencias, y **te lo dice antes de empezar**. Cuando dices «sí», varios **sub-agentes**
trabajan a la vez (3 por defecto); lo que produce un paso (por ejemplo, la investigación con fuentes) se le pasa a los
que dependen de él. Ves el avance en el HUD y el reactor; «¿cómo va el proyecto?», «cancela el proyecto». Al terminar
te avisa (también por Telegram si lo pediste desde allá) y todo queda en *Documentos\Jarvis\Proyectos\<nombre>*, con
un «Resumen del proyecto». Si un paso falla, los demás siguen; si Jarvis se cierra a mitad, al volver te pregunta si
lo continúa.

**Centro de aprobaciones.** Lo importante que Jarvis va a hacer por su cuenta te lo pregunta primero (hoy, los
proyectos; desde la 7.7, correos, eventos y la casa). Respondes por voz («sí», «sí 3», «no 2»), en *Ajustes › Agente*,
en el panel del celular (botones Aprobar/Rechazar), en Telegram o con clic derecho en el reactor (un **punto violeta**
avisa que hay algo esperando). Si nadie responde en 15 minutos, no se hace. **Solo tú apruebas**: ni un enlace
`jarvis://` (que podría venir de una web), ni otra IA por MCP, ni una tarea programada pueden aprobar nada. Todo queda
en el **registro de acciones**: «¿qué hiciste por tu cuenta hoy?», «¿qué tengo por aprobar?».

El reactor de Windhawk pasa a la versión 2.1 (punto violeta y «Aprobar/Rechazar» en su menú): cópialo otra vez desde
*Ajustes › Integraciones*.

## Herramientas por significado, habilidades de la comunidad e investigaciones con fuentes (v7.5)

**Investiga a fondo, con fuentes.** «**Investiga a fondo la deforestación en la Amazonía**», «investiga el ciclo del
agua», «hazme un informe sobre el reciclaje»: Jarvis planea varias búsquedas, junta hasta 8 fuentes distintas, lee cada
página y te deja un **documento de Word** en *Documentos\Jarvis\Investigaciones* con título, resumen, secciones, ideas
«Para llevar al aula» y **cada dato citado [1], [2]…**, con la lista de fuentes y sus enlaces al final. Te dice el
resumen en voz alta. Sin IA, el documento recoge lo que dice cada fuente (también citado). «Busca en internet…» y
«averigua…» siguen siendo la respuesta rápida en voz. Desde Telegram, una tarea programada («cada viernes a las 5
investiga noticias de educación y mándamelo al celular») o Claude Desktop también funciona: te llega el resumen.

**Habilidades de la comunidad (OpenClaw, Hermes, Claude).** En *Ajustes › Rutinas* importas habilidades en el formato
`SKILL.md` (agentskills.io) desde un archivo `.md`/`.zip` o desde el enlace a su carpeta en GitHub. Jarvis importa
**solo sus instrucciones**: cuando lo que pides encaja con su descripción, su IA responde siguiéndolas. **Nunca
ejecuta sus programas.** Antes de instalar, un **revisor de seguridad** te muestra lo que encontró: instrucciones para
engañar a la IA («ignora las instrucciones anteriores», «no le digas al usuario»), intentos de sacar claves o
archivos, comandos que descargan y ejecutan código, texto escondido (caracteres invisibles, bloques codificados) y las
webs que menciona. Con riesgo alto no se instala. Vienen dos de ejemplo: **planificador de clases** («ayúdame a planear
una clase de fracciones para quinto») y **rúbrica de evaluación**. Entran en las copias de seguridad.

**Herramientas por significado.** Con muchos conectores MCP, la IA solo ve los que tienen que ver con lo que pides (las
acciones propias de Jarvis las ve siempre): responde más rápido y se equivoca menos. Con tu clave de Gemini (o un
modelo de embeddings en Ollama) los elige por significado; sin ellos, por palabras. Se ajusta en *Ajustes › Control
del PC › Interpretación de órdenes*.

## Aprende tus costumbres, recuerda lo que hablaron y hace tareas solo (v7.4)

**Aprende de lo que haces.** Si varios días repites las mismas órdenes seguidas (por ejemplo «abre Word», «volumen
al 30», «pon música para concentrarse»), Jarvis te pregunta: *¿Quieres que lo guarde como una rutina?* Respondes
«sí» o «sí, llámala modo escribir», y desde entonces basta con decir «modo escribir». Si haces algo casi siempre a la
misma hora, te propone hacerlo solo («¿lo hago yo a las 7:30 de lunes a viernes?»). Y si justo después de una rutina
cambias algo que ella hizo («volumen al 25» tras una rutina que lo pone al 40), te propone corregirla para la próxima
vez. Como mucho 3 propuestas al día, nunca en tus horas de silencio, y lo que rechaces no te lo vuelve a proponer. No
aprende de lo que llega por el celular, por enlaces ni de los pasos de las rutinas. «Olvida mis costumbres» lo borra.

**Memoria buscable.** Pregúntale **«¿qué te dije la semana pasada sobre el examen de 7A?»**, **«¿de qué hablamos
ayer?»**, **«busca en mi memoria la reunión de padres»** o **«¿te acuerdas de lo que te conté del paseo?»**. Busca en
todo el historial de conversaciones, entiende fechas («ayer», «la semana pasada», «en octubre», «el lunes») y, con la
IA, te responde en una frase diciendo cuándo fue. Busca por palabras (con tildes, plurales y palabras parecidas) y,
si tienes la clave de Gemini o un modelo de embeddings en Ollama, también **por significado** («la prueba» encuentra
«el examen»). Antes de guardar nada tapa correos, claves, contraseñas y números de tarjeta. Se ajusta y se borra en
*Ajustes › Memoria*, y entra en las copias de seguridad.

**Tareas programadas que trabajan solas.** «**Cada lunes a las 6 de la tarde resume mis pendientes y mándamelo al
celular**», «todos los días a las 7 de la mañana dime el clima», «de lunes a viernes a las 6:30 dime qué tengo hoy»,
«cada viernes a las 5 pm investiga noticias de educación y envíamelo por Telegram». Jarvis la hace a su hora y te
entrega lo que conteste: en voz alta, en tu celular (Telegram) o las dos cosas. Si el equipo estaba apagado, la hace
al encenderlo (si no pasaron más de 6 horas). «¿Qué tareas tengo programadas?», «borra la tarea del clima», «pausa la
tarea de los pendientes». También en *Ajustes › Rutinas › Tareas programadas*, con botón para probarlas. Se hacen con
las reglas del celular: nada de apagar, cerrar programas, escribir en ventanas ni borrar.

## Corrección del reactor (v7.3.1)

El mod del reactor (2.0.1) ya compila en Windhawk: dos opciones de sus ajustes llevaban «:» en el texto y Windhawk
no podía leer la lista de ajustes. Copia otra vez el código en Windhawk (*Ajustes › Integraciones › Copiar el código
del mod*) y pulsa *Compilar*.

## El reactor de Jarvis en la barra de tareas (v7.3)

El orbe de la 7.2 ahora es un **mini reactor** (mod de Windhawk `windhawk/jarvis-orbe.wh.cpp`, versión 2.0): bisel
metálico con marcas que giran, diez bobinas, anillo interior y un núcleo que brilla, todo del color de tu tema.
- **Te escucha**: las bobinas se encienden con tu voz, como un medidor de nivel. **Piensa**: un destello ámbar gira
  por las bobinas. **Habla**: todo late al ritmo de la voz. **Micrófono en pausa**: gris. **Cerrado**: núcleo rojo.
- **Temporizador**: un arco ámbar alrededor que se va vaciando (parpadea el último medio minuto).
- **Avisos**: destello rojo-ámbar y una tarjeta con el recordatorio. **Respuestas**: una onda blanca desde el núcleo
  y, si el panel está oculto, una burbuja con lo que te dijo.
- **Pasar el ratón**: una tarjeta con su estado, el temporizador con cuenta atrás y barra, lo próximo de hoy, la IA
  y lo último que te dijo.
- **Clic**: háblale. **Doble clic**: mostrar u ocultar el panel. **Mayús+clic**: un cuadro para escribirle sin abrir
  el panel. **Rueda**: volumen. **Clic central**: pausa o reanuda la música. **Arrastrar**: cambiarlo de sitio.
  **Clic derecho**: menú con modo clase, temporizadores de 5 y 10 minutos, pendientes, música, micrófono, prueba
  completa y ajustes.

Para actualizarlo: en Windhawk, abre el mod del orbe › *Editar*, reemplaza el código por el nuevo (*Ajustes ›
Integraciones › Copiar el código del mod*) › *Compilar*.

## Jarvis dentro de Windows y el orbe de la barra de tareas (v7.2)

**Integrar Jarvis con Windows** (*Ajustes › Integraciones › Jarvis dentro de Windows*). Con un interruptor:
- **Clic derecho en el escritorio o en una carpeta › Jarvis**: *Mostrar Jarvis*, *Escribir una orden…*, *Modo clase*,
  *Temporizador de 5 minutos*, *¿Qué tengo pendiente?*, *Pausar el micrófono*, *Prueba completa* y *Ajustes*.
  En Windows 11 está en «Mostrar más opciones» (o Shift+F10).
- **Win+R › `jarvis`** abre Jarvis (y `jarvis:` también).
- **Lista de saltos**: clic derecho en el icono de Jarvis en la barra de tareas › *Escribir una orden*, *Modo clase*,
  *Temporizador*, *Micrófono*, *Ajustes*.
- **Enlaces `jarvis://`** para tus propios accesos directos o botones: `jarvis://rutina/Modo clase`,
  `jarvis://temporizador/10`, `jarvis://orden/qué tengo hoy`, `jarvis://escribir`, `jarvis://mostrar`.
- **Notificaciones de Windows**: los recordatorios, la agenda, los temporizadores y lo que vigilas salen también en el
  centro de notificaciones, con botones *Posponer 5 min*, *Posponer 15 min* u *Otros 5 minutos*.

Solo cambia tu usuario de Windows (sin permisos de administrador), y al apagar el interruptor se quita todo. Las
órdenes que llegan por un enlace siguen las reglas del celular: nada de apagar, cerrar programas, escribir en
ventanas ni borrar datos, porque un enlace también podría venir de una página web.

**El orbe de Jarvis en la barra de tareas** (mod de Windhawk, en la carpeta `windhawk/`). El reactor de Jarvis junto
al reloj: cian cuando está atento, brillante cuando te escucha, ámbar girando cuando piensa, verde cuando habla, gris
con el micrófono en pausa y apagado si Jarvis está cerrado; un punto ámbar si hay un temporizador (pasa el ratón para
ver cuánto falta). **Clic**: háblale. **Clic derecho**: menú de órdenes. Para instalarlo: instala Windhawk
(windhawk.net) › *Crear un nuevo mod* › borra el ejemplo y pega el código (botón *Copiar el código del mod* en
Ajustes) › *Compilar* › *Activar*. Se comunica con Jarvis solo dentro de tu equipo y con un código secreto que
cambia cada vez que Jarvis arranca.

## Bienvenida, respuestas más rápidas y copias completas (v7.1)

**Bienvenida.** La primera vez que abres Jarvis aparece una guía de cinco pasos: cómo quieres que te llame y tu
color, el micrófono (dices «Jarvis, ¿qué hora es?» y te confirma que te oyó), la voz (con botón para escucharla), la
IA (Gemini gratis con su clave, Ollama en tu equipo u otra) y una prueba con frases que puedes tocar. Si ya usabas
Jarvis no te salta; la repites cuando quieras con **«repite la bienvenida»**, desde *Ajustes › Acerca de* o desde el
icono de la bandeja.

**Responde más rápido, y sabe por qué tarda.** Las frases cortas que más se repiten («¿Sí?», «Hecho», «Listo», los
saludos…) se guardan ya convertidas en voz y suenan al instante, sin volver a pedirlas a internet; al arrancar deja
listas las más comunes (con la voz de Microsoft o Piper; la de Gemini no, para no gastar tu cuota). Además mide cada
respuesta por etapas (reconocer tu voz, pensar, generar la voz, empezar a sonar): pregúntale **«¿qué tan rápido
respondes?»** o **«¿por qué tardas tanto?»** y te dice su tiempo medio, qué etapa es la más lenta y qué cambiar. El
registro anota cada tiempo (TIEMPOS) y la prueba completa avisa si va lento.

**Copias de seguridad completas.** Ahora la copia también guarda **lo que Jarvis sabe de ti**, tus **habilidades
instaladas** y el **diario**, y al restaurarla los recarga sin reiniciar. Las copias se revisan al restaurar: nada
puede escribirse fuera de la carpeta de Jarvis.

**Por dentro, ordenado.** `jarvis.py` pasó de 9.000 líneas a unas 1.700: cada área vive ahora en su propio archivo
dentro de la carpeta `nucleo/` (voz, IA, escucha, ventanas, aula, avisos, diagnóstico…). Funciona igual, pero es más
fácil de mantener y de revisar; las pruebas automáticas comprueban que todas las partes encajan.

## Jarvis 7.0: habla primero, se conecta a todo y se ve de película (v7.0)

**Habla primero, con criterio.** Sin que preguntes, Jarvis avisa cuando de verdad ayuda: el **saludo de la mañana**
(la primera vez que usas el equipo: la hora, el clima en una frase y lo que tienes hoy), **«¿activo el modo clase?»**
unos minutos antes de una clase de tu calendario (si dices «sí», la lanza), **lluvia a tu hora de salida**, una
**pausa** tras dos horas seguidas en el equipo y la **batería baja**. Nunca en tus horas de silencio (21:30–06:30 por
defecto), como mucho 12 avisos al día y al menos 15 minutos entre uno y otro. Todo se ajusta en *Ajustes › General*.

**Tarjetas holográficas.** Cuando Jarvis te cuenta el clima, tu agenda, una rutina (con su barra de pasos), un aviso
o el resultado de la prueba completa, también lo ves en una tarjeta animada en el HUD, con los números resaltados.

**Conectores MCP.** MCP es el estándar con el que Claude, Goose o Jan se conectan a otras apps. En *Ajustes ›
Integraciones › Conectores MCP* pegas la configuración (el mismo formato que Claude Desktop) y Jarvis le enseña esas
herramientas a su IA: cuando le pides algo que encaja, la usa, **preguntándote antes** salvo en los conectores que
marques como de confianza. Funciona con conectores locales (`command`) y remotos (`url` con su token).
Y al revés: activa **«Dejar que otras IA usen Jarvis»** y Claude Desktop podrá darle órdenes («pon un temporizador»,
«¿qué tengo hoy?»), con las mismas reglas que el celular. Jarvis te muestra la configuración exacta para copiarla.

**Habilidades instalables.** Una habilidad es un archivo `.json` que le enseña algo nuevo: frases con huecos
(`busca {tema} en wikipedia`) y qué hacer (abrir una web, decir algo, preguntarle a la IA o una lista de órdenes).
Vienen cuatro de ejemplo (Wikipedia, Traductor, Modo concentración, Dato del día). Se instalan, se quitan y se
**comparten** en *Ajustes › Rutinas › Habilidades instaladas*: pásale a un colega tu habilidad en un archivo.

**Diario.** Jarvis anota lo que haces con él (órdenes, rutinas, temporizadores, avisos) para responder **«¿qué hice
ayer?»**, **«¿qué hice hoy?»** o **«resume mi semana»** (con la IA, un resumen humano; sin ella, las cifras), y para que
la IA sepa en qué estás hoy. Solo en tu equipo, se borra solo pasados 30 días y nunca anota lo que suene a contraseña.

**«Avísame cuando termine…».** «Avísame cuando termine la descarga», «avísame cuando se cierre Zoom», «avísame cuando
termine de instalar» o «cuando Premiere termine»: Jarvis vigila y te avisa con un tono y la voz (y por Telegram si te
fuiste). «¿Qué estás vigilando?», «deja de vigilar».

**Panel en el celular.** En *Ajustes › Integraciones › Panel en el celular* lo activas y escaneas el código QR: el
celular muestra el reactor, la conversación, tus temporizadores, lo de hoy y botones rápidos (pausa, volumen, clima,
10 minutos, prueba completa…). Solo en tu wifi y con un código secreto; con las mismas reglas de seguridad que Telegram.

**Lee el tablero.** «Lee lo que hay en el tablero» o «pasa esta hoja a Word»: Jarvis toma una foto con la cámara,
transcribe el texto (con fórmulas), lo guarda en Word en la carpeta *Tablero* y lo copia al portapapeles. Y **«haz un
quiz con lo que hay en el tablero»** convierte lo fotografiado en un quiz o taller listo en Word.

Nuevo componente: `qrcode` (para el código del panel). Si actualizas desde Ajustes, Jarvis lo instala solo.



## Prueba completa, rutinas solas, memoria de tu gente y más (v6.8)

**Prueba completa.** Di **«Jarvis, prueba completa»** (o «revisa todo»), pulsa *Ajustes › Acerca de › Hacer la
prueba completa* o escribe **/prueba** en Telegram. Revisa el micrófono, el modelo de voz, la voz, internet, la IA
(y la IA local para cuando no hay internet), Telegram, el calendario y si hay versión nueva. Cada cosa sale en verde,
ámbar o rojo, con un botón para arreglarla, y **Copiar el informe** te lo deja listo para pegarlo donde pidas ayuda.

**Rutinas que se lanzan solas.** En *Ajustes › Rutinas*, el campo nuevo **«Lanzarla sola»**:
`07:30` (todos los días), `07:30 lun-vie`, `21:00 sab,dom`, **`al iniciar`** (al encender el equipo) o
**`al volver`** (cuando vuelves al equipo tras 10 minutos o más sin usarlo). Con la IA conectada también se piden
hablando: «crea una rutina buenos días a las 7 de lunes a viernes que diga el clima y mis pendientes».

**Te entiende las peticiones con forma de pregunta.** «¿Puedes subir el volumen?», «¿me abres la calculadora?» o
«¿me pones un temporizador de 5 minutos?» antes se tomaban como preguntas: la IA contestaba, pero no se hacía nada.
Ahora se hacen. Y la IA interpreta mejor lo que no se dice como orden («está muy oscuro aquí» sube el brillo).

**La memoria aprende tu gente y tus gustos.** «Mi hermana se llama Ana», «mi perro se llama Rocky», «me gusta el
vallenato», «tengo dos gatos», «mi color favorito es el azul»… Un dato nuevo sobre lo mismo corrige al viejo
(«mi hermana se llama Laura» → «Entendido, lo corrijo»). Pregúntale «¿cómo se llama mi hermana?», «¿qué música me
gusta?» o «¿qué sabes de mí?». Ahora recuerda hasta 200 cosas y a la IA le pasa las que vienen al caso.

**Desde el celular, más seguro.** Además de apagar o reiniciar, por Telegram tampoco cierra programas, ni escribe en
ventanas, ni borra notas, memoria o rutinas, ni instala actualizaciones (aunque la IA lo eligiera).

**«Actualízate».** Por voz instala la versión nueva, siempre preguntando antes. Y antes de instalar comprueba que el
archivo descargado es exactamente el publicado (tamaño y huella SHA-256).

**Para quien mantiene Jarvis.** El repositorio tiene ahora pruebas automáticas (`tests/`, con las frases de
`tests/frases.txt`) y GitHub las pasa en cada cambio en Windows. Al subir `VERSION` en `jarvis.py`, si todas pasan,
GitHub empaqueta y publica la Release `vX.Y` sola (ya no hace falta `empaquetar_version.py` a mano).
Para ejecutarlas en tu equipo: `pip install pytest` y `python -m pytest tests`.



## Manejar el navegador por voz (v6.7)

Ahora Jarvis puede moverse por el navegador mientras lo usas (por ejemplo en YouTube o leyendo una página):
- **«busca el ciclo del agua en una pestaña nueva»** — abre una pestaña y hace la búsqueda.
- **«cambia de pestaña»**, **«pestaña anterior»**, **«ve a la pestaña 3»**, **«cierra la pestaña»**, **«reabre la pestaña»**, **«abre una pestaña nueva»**.
- **«busca la palabra fotosíntesis en la página»** (como Ctrl+F).
- **«baja la página»**, **«sube la página»**, **«ve al final»**, **«ve atrás»**, **«adelante»**, **«recarga la página»**.
- Y lo de siempre: **«busca X en YouTube»**, **«busca X en Google»**, **«pausa»/«siguiente»** para el video.

Para las órdenes de teclado (cambiar de pestaña, buscar en la página, desplazar), tu navegador debe estar
visible; Jarvis lo pone al frente y envía la tecla. Abrir una pestaña con una búsqueda funciona siempre.
Lo que Jarvis todavía no hace es hacer clic dentro de la página ni elegir un resultado por ti: abre la
búsqueda y tú das el clic final.

## HUD más futurista y nuevos colores (v6.6)

El panel se ve más vivo y elegante, sin perder legibilidad:
- El **reactor brilla al ritmo de tu voz** (crece y se ilumina mientras hablas) y «respira» despacio en reposo.
- **Vidrio con profundidad:** fondo con capas, una rejilla muy sutil y un brillo tenue en los bordes.
- **Esquinas tipo visor** (como una nave), los indicadores laten suave y el nombre «JARVIS» brilla al escuchar o hablar.
- **Más colores de tema** en *Ajustes › General › Apariencia*: además de cian, ámbar, rojo, verde y violeta, ahora hay **azul profundo, magenta y blanco frío**.

## Buscar en internet y arranque más rápido (v6.5)

**Búsqueda web hablada.** Di «busca en internet qué pasó con la reforma educativa», «averigua cuándo
es el día del maestro» o «busca la biografía de Policarpa y resúmemela». Jarvis busca en internet
(DuckDuckGo, sin clave), lee los primeros resultados y te los **resume en voz**, y deja las fuentes
en el Registro. Es distinto de «busca X en Google», que abre el navegador: esto te lo cuenta en voz.

**Arranca más rápido.** Jarvis ahora queda «en línea» mucho antes: el panel y el servidor se abren
primero, y lo pesado (el modelo de voz, el motor de voz Piper con su onnxruntime, el índice de
aplicaciones, la IA) se carga en segundo plano sin frenar el arranque. Además, si el puerto está
libre ya no revisa todos los procesos del equipo al iniciar. (Recuerda: si Jarvis está dentro de
OneDrive, la sincronización lo vuelve lento; tenerlo en C:\Jarvis ayuda mucho.)

## Sismos, memoria que aprende sola, correo por voz y detalles (v6.4)

**Alerta de sismos.** Actívala en *Ajustes › Integraciones › Alerta de sismos*. Con los datos del
USGS (gratis), Jarvis vigila los temblores y, si uno es relevante **para tu zona** (usa tu ciudad del
apartado Clima), te avisa con un tono y por voz: tono suave para los moderados, tono de alerta y
recomendaciones de seguridad para los fuertes y cercanos. Los lejanos o pequeños no te molestan.

**Memoria que aprende sola.** Cuando le cuentas algo tuyo («trabajo en el colegio San José»,
«prefiero respuestas cortas», «dicto ciencias en séptimo»), Jarvis lo recuerda **sin que digas
“recuerda”** y lo tiene en cuenta al responder. Lo ves y lo borras en *Ajustes › Memoria › Lo que
Jarvis ha aprendido de ti*, o le dices «olvida que…».

**Correo por voz (Gmail).** En *Ajustes › Integraciones › Correo por voz* pon tu Gmail y una
**contraseña de aplicación** (16 letras, de la seguridad de tu cuenta de Google; no tu clave normal),
y una agenda de correos. Luego di «escríbele un correo a la coordinadora diciendo que mañana llego a
las 7»: Jarvis lo redacta, **te lo lee y solo lo envía si confirmas** («sí, envíalo» / «no»).

**Detalles.**
- **Cómo te llama:** en *Ajustes › General › Trato* escribe «profe» o tu nombre, o dilo: «llámame profe».
- **Apagado programado:** «apaga el pc a las 6», «apaga en 30 minutos» (te pide confirmar).
- **Descansar:** «Jarvis, descansa» se despide con un tono suave y se oculta; «Jarvis, despierta» vuelve.

## Clima, noticias y control desde el celular (v6.3)

**Clima y noticias.** En *Ajustes › Integraciones › Clima y noticias* escribe tu ciudad y pulsa
«Probar clima». Luego di **«¿cómo está el clima?»**, **«¿va a llover mañana?»** o **«clima en Cali»**:
Jarvis dice la temperatura, la humedad, la probabilidad de lluvia (con la hora en que empieza) y
recomendaciones para el día (paraguas, bloqueador si el sol estará fuerte, abrigo si hará frío). Di
**«noticias»** o **«noticias de educación»** para un resumen hablado de los titulares del día. Puedes
activar que el **reporte de la mañana** incluya el clima y las noticias. El clima es de Open-Meteo,
gratis y sin clave; las noticias, de Google Noticias Colombia y BBC Mundo (puedes cambiar las fuentes).

**Controlar Jarvis desde el celular (Telegram).** En *Ajustes › Integraciones › Telegram*:
1. Crea un bot con `@BotFather` en Telegram y pega su token.
2. Pulsa «Probar», escríbele «hola» al bot y Jarvis te dirá tu **chat id**; pégalo y guarda.
3. Activa **«Controlar Jarvis desde el celular»**.

Entonces, desde donde estés, le escribes como le hablarías: «¿qué tengo hoy?», «abre la presentación
de ciencias», «recuérdame a las 3 llamar a la coordinadora», «¿cómo está el clima?». Comandos
rápidos: `/captura` (foto de la pantalla), `/estado`, `/ayuda`. Solo obedece a tu chat; cualquier
otro se ignora. Por seguridad, **apagar, reiniciar, cerrar sesión o borrar no se hacen desde el
celular**. Con **«Enviarme los avisos al celular»** activado, los recordatorios, los avisos del
calendario, los temporizadores y el reporte de la mañana también te llegan por Telegram.

## Jarvis ve en vivo, y presentaciones y Excel por voz (v6.2)

**Ver en vivo.** En la conversación en vivo di **«mira esto»** y muéstrale algo a la cámara (un
cuaderno, un experimento, un dibujo), o **«mira mi pantalla»** para que te guíe con lo que tienes
abierto. Con Gemini Live lo ve como video (una imagen por segundo) y comenta mientras hablas; con
OpenAI Realtime ve una foto cada vez que se lo pides. Di **«deja de mirar»** para parar (se detiene
solo a los 3 minutos o al terminar la conversación). El HUD muestra «VIENDO CÁMARA/PANTALLA».
Nunca mira ventanas de contraseñas, bancos, pagos ni navegación privada: si cambias a una, deja de
enviar imágenes mientras esté abierta.

**Presentaciones.** «Haz una presentación de 8 diapositivas sobre el ciclo del agua para quinto»:
portada con tu colegio y tu nombre, diapositivas de contenido, una pregunta para pensar y una
actividad al final, y **notas para ti** debajo de cada diapositiva (qué decir o preguntar). Queda en
*Documentos › Jarvis › Material de clase* y se abre en PowerPoint.

**Planilla de notas.** «Crea la planilla de notas de 7A con 4 notas del segundo periodo»: la lista del
curso (del tablero del aula), promedio y desempeño automáticos, colores por desempeño, notas en rojo
si están en Bajo, resumen del curso y solo acepta notas de 1,0 a 5,0. La escala (Superior, Alto,
Básico, Bajo) está en la hoja «Escala»: cámbiala según el SIEE de tu colegio y todo se recalcula.

**Tablas.** «Crea una tabla en Excel de los planetas con su distancia al sol»: la IA arma la tabla con
números de verdad (para ordenar, filtrar y graficar). Quedan en *Documentos › Jarvis › Planillas*.

## Otros proveedores de voz en vivo (v6.1)

En *Ajustes › Escucha › Proveedor de voz en vivo* puedes elegir quién conversa contigo en vivo:

| Proveedor | Costo | Clave |
|---|---|---|
| **Gemini Live** (recomendado) | Gratis con límites diarios | La de Gemini (sección IA) |
| **OpenAI Realtime** (la voz de ChatGPT) | De pago | La de ChatGPT (sección IA) |
| **Deepgram** | 200 USD de crédito al registrarte, sin tarjeta | La de console.deepgram.com |

Con **«Si falla, usar otro»** activado, si el elegido no responde o se le acaba la cuota, Jarvis
prueba solo los otros que tengan clave, y si ninguno puede, usa el modo clásico. **Probar conexión
en vivo** revisa todos y te dice cuál funciona. En todos, las acciones en el PC las hace Jarvis y
apagar, reiniciar o borrar no se hacen desde la conversación en vivo.

## Conversación en vivo con Gemini Live (v6.0)

Antes, Jarvis escuchaba por pasos: un reconocedor pasaba tu voz a texto, la IA respondía en texto y
otra voz lo leía. Cada paso podía equivocarse o cortar la frase. Ahora, después de decir **«Jarvis»**,
tu voz va **directo a Gemini Live**, el modo de voz en tiempo real de Gemini (el mismo que usan los
asistentes que «entienden como una persona»):

- Gemini **oye tu voz tal cual**: acentos, ruido, pausas, nombres. Nada se pierde al pasar a texto.
- **Sabe solo cuándo terminaste** de hablar (no corta tus frases ni espera de más).
- Responde con **voz natural** (la que elegiste en *Voz › Gemini*) y puedes **interrumpirlo**.
- **Sigues conversando sin repetir «Jarvis»**; la conversación termina sola tras 15 s de silencio o
  cuando te despides («gracias, eso es todo»).
- **Hace cosas en tu PC:** cuando le pides una acción («abre Word», «manda un WhatsApp a Andrea…»,
  «pon un temporizador»), Gemini se la pide a Jarvis, que la ejecuta y le cuenta el resultado.
  Por seguridad, apagar, reiniciar o borrar **no** se hacen desde la conversación en vivo.
- **Privacidad igual que antes:** lo que se habla en el salón sin decir «Jarvis» nunca sale de tu PC;
  el reconocimiento local solo busca la palabra «Jarvis».
- Si Gemini Live no está disponible (sin internet, sin clave, sin cuota), Jarvis usa solo el modo
  clásico y lo explica en el Registro.

Se configura en *Ajustes › Escucha › Cómo conversas con Jarvis* (Automático, Siempre en vivo o
Clásico) y tiene un botón **Probar conexión en vivo**. Consejo: con audífonos funciona aún mejor;
con parlantes, si se interrumpe solo, sube «Fuerza de voz para interrumpirlo».

## Escucha más paciente (v5.11)

- **La espera cuenta desde que empiezas a hablar.** Antes, si decías «Jarvis», esperabas un momento y
  dabas una orden larga, la ventana se cerraba mientras aún hablabas y la orden se perdía. Ahora vale
  si la *empezaste* a tiempo. Además, la espera tras decir «Jarvis» sube a 10 segundos.
- **Más órdenes seguidas sin repetir «Jarvis»** (hasta 8), pero solo lo que suena a orden o pregunta
  («abre…», «cierra…», «¿qué hora es?»): una conversación o un video de fondo no se toma como orden.
- **«Mostrar panel»** funciona sin decir «Jarvis», como indica el aviso del modo sigilo.
- Si una orden llega cuando ya dejó de escucharte, el Registro lo dice y te explica qué hacer.

## Te entiende mejor (v5.10)

Cambios hechos a partir de un registro real de uso:
- **Tu «Jarvis» ya no se pierde.** Con la «Sensibilidad del micrófono» subida (para ignorar un video o
  el ruido del salón) también se descartaba tu propia voz. Ahora la sensibilidad nunca descarta una
  frase en la que lo llamas por su nombre; sigue ignorando el resto del ruido.
- **«Jarvis» donde quieras:** «abre Word, Jarvis» o «oye, Jarvis, abre Word» también funcionan.
- **El «¿Sí?» ya no tapa tu orden:** mientras Jarvis dice «¿Sí?», ya te está escuchando, así que
  puedes hablar de inmediato.
- **Seguir la conversación:** después de responderte, sigue escuchando unos segundos (6 por defecto),
  así que puedes decir «ahora ciérralo» sin repetir «Jarvis» (hasta 3 órdenes seguidas). Se ajusta
  en *Ajustes › Escucha › Seguir la conversación* (0 = siempre decir «Jarvis»).
- **Calendario:** entiende «revisa mi calendario», «¿qué eventos hay en mi calendario?», «¿qué tengo
  en la agenda mañana?»… y si aún no está conectado, te dice cómo conectarlo.

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
1. El repositorio oficial ya viene puesto: `zaiddia/Jarvis` (puedes cambiarlo si publicas en otro).
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
