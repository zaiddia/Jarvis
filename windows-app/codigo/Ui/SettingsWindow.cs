using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Jarvis.Core;
using Jarvis.Speech;

namespace Jarvis.Ui
{
    // Ventana de ajustes, construida en código. Trabaja sobre una copia y la entrega al guardar.
    public sealed class SettingsWindow : Window
    {
        readonly Settings _s;
        readonly List<Action> _commit = new List<Action>();
        public event Action<Settings> Saved;
        public Func<Settings, System.Threading.Tasks.Task<string>> TestAi;
        public Action<Settings, string> TestVoice;
        public Action RunDiagnostics;
        public Action RunFullCheck;
        public Func<bool, System.Threading.Tasks.Task<string>> CheckUpdates;
        public Func<string> NewTopic;

        static Settings Clone(Settings s) => JsonSerializer.Deserialize<Settings>(JsonSerializer.Serialize(s));

        public SettingsWindow(Settings current)
        {
            _s = Clone(current);
            Title = "Ajustes de " + current.Name;
            Width = 640;
            // Nunca más alta que la pantalla (con portátiles de 768 px se salía).
            Height = Math.Min(660, SystemParameters.WorkArea.Height - 40);
            MinWidth = 520;
            MinHeight = Math.Min(480, SystemParameters.WorkArea.Height - 40);
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            FontFamily = new FontFamily("Segoe UI Variable Text, Segoe UI");
            FontSize = 13;
            try { Icon = System.Windows.Media.Imaging.BitmapFrame.Create(new Uri("pack://application:,,,/jarvis.ico")); } catch { }

            var dock = new DockPanel();
            var header = new Border
            {
                Background = new LinearGradientBrush(Color.FromRgb(0x04, 0x14, 0x26), Color.FromRgb(0x0B, 0x3A, 0x5E), 0),
                Padding = new Thickness(20, 14, 20, 14),
                Child = new StackPanel
                {
                    Children =
                    {
                        new TextBlock { Text = current.Title, Foreground = new SolidColorBrush(Color.FromRgb(0xE8, 0xF6, 0xFF)), FontSize = 20, FontWeight = FontWeights.SemiBold, FontFamily = new FontFamily("Bahnschrift, Segoe UI") },
                        new TextBlock { Text = "Asistente personal por voz · versión " + typeof(SettingsWindow).Assembly.GetName().Version.ToString(3), Foreground = new SolidColorBrush(Color.FromRgb(0x86, 0xA9, 0xC2)) },
                    },
                },
            };
            DockPanel.SetDock(header, Dock.Top);
            dock.Children.Add(header);

            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(12) };
            var save = new Button { Content = "Guardar", Width = 110, Height = 30, IsDefault = true, Margin = new Thickness(0, 0, 8, 0) };
            var cancel = new Button { Content = "Cancelar", Width = 110, Height = 30, IsCancel = true };
            save.Click += (o, e) =>
            {
                foreach (var a in _commit) a();
                Saved?.Invoke(_s);
                Close();
            };
            buttons.Children.Add(save);
            buttons.Children.Add(cancel);
            DockPanel.SetDock(buttons, Dock.Bottom);
            dock.Children.Add(buttons);

            var tabs = new TabControl { Margin = new Thickness(12, 12, 12, 0) };
            tabs.Items.Add(Tab("General", General()));
            tabs.Items.Add(Tab("Voz", Voice()));
            tabs.Items.Add(Tab("Inteligencia", Intelligence()));
            tabs.Items.Add(Tab("Agenda", Agenda()));
            tabs.Items.Add(Tab("Integraciones", Integrations()));
            tabs.Items.Add(Tab("Aspecto", Look()));
            tabs.Items.Add(Tab("Rutinas", Protocols()));
            tabs.Items.Add(Tab("Memoria", MemoryTab()));
            tabs.Items.Add(Tab("Acerca de", About()));
            dock.Children.Add(tabs);
            Content = dock;
        }

        static TabItem Tab(string name, UIElement content) => new TabItem
        {
            Header = name,
            Content = new ScrollViewer { Content = content, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Padding = new Thickness(16, 12, 16, 12) },
        };

        // ---------------------------------------------------------------- piezas

        static Grid Form()
        {
            var g = new Grid();
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(190) });
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            return g;
        }

        static void Row(Grid g, string label, UIElement control, string hint = null)
        {
            int r = g.RowDefinitions.Count;
            g.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var l = new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 6, 10, 6), TextWrapping = TextWrapping.Wrap };
            Grid.SetRow(l, r);
            g.Children.Add(l);
            UIElement c = control;
            if (hint != null)
                c = new StackPanel { Children = { control, new TextBlock { Text = hint, Foreground = Brushes.Gray, FontSize = 11.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 0) } } };
            if (c is FrameworkElement fe) fe.Margin = new Thickness(0, 5, 0, 5);
            Grid.SetRow(c, r);
            Grid.SetColumn(c, 1);
            g.Children.Add(c);
        }

        static void Section(Grid g, string title)
        {
            int r = g.RowDefinitions.Count;
            g.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var t = new TextBlock { Text = title, FontWeight = FontWeights.SemiBold, FontSize = 14, Margin = new Thickness(0, r == 0 ? 0 : 16, 0, 4), Foreground = new SolidColorBrush(Color.FromRgb(0x0B, 0x5C, 0x8E)) };
            Grid.SetRow(t, r);
            Grid.SetColumnSpan(t, 2);
            g.Children.Add(t);
        }

        TextBox Str(Func<string> get, Action<string> set)
        {
            var t = new TextBox { Text = get(), Padding = new Thickness(3) };
            _commit.Add(() => set(t.Text.Trim()));
            return t;
        }

        PasswordBox Secret(Func<string> get, Action<string> set)
        {
            var t = new PasswordBox { Password = get(), Padding = new Thickness(3) };
            _commit.Add(() => set(t.Password.Trim()));
            return t;
        }

        CheckBox Bool(string text, Func<bool> get, Action<bool> set)
        {
            var c = new CheckBox { Content = text, IsChecked = get(), VerticalAlignment = VerticalAlignment.Center };
            _commit.Add(() => set(c.IsChecked == true));
            return c;
        }

        // Opciones (valor guardado, texto visible).
        ComboBox Choice(Func<string> get, Action<string> set, params (string value, string label)[] options)
        {
            var c = new ComboBox();
            foreach (var o in options) c.Items.Add(new ComboBoxItem { Content = o.label, Tag = o.value });
            c.SelectedItem = c.Items.Cast<ComboBoxItem>().FirstOrDefault(i => (string)i.Tag == get()) ?? c.Items[0];
            _commit.Add(() => set((string)((ComboBoxItem)c.SelectedItem).Tag));
            return c;
        }

        // Lista editable (se puede escribir otro valor).
        ComboBox Editable(Func<string> get, Action<string> set, IEnumerable<string> options)
        {
            var c = new ComboBox { IsEditable = true, Text = get() };
            foreach (var o in options) c.Items.Add(o);
            c.Text = get();
            _commit.Add(() => set(c.Text.Trim()));
            return c;
        }

        Slider Range(int min, int max, Func<int> get, Action<int> set, out TextBlock valueLabel)
        {
            var s = new Slider { Minimum = min, Maximum = max, Value = get(), IsSnapToTickEnabled = true, TickFrequency = 1, Width = 260, HorizontalAlignment = HorizontalAlignment.Left };
            var lbl = new TextBlock { Text = get().ToString(), Margin = new Thickness(10, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center };
            s.ValueChanged += (o, e) => lbl.Text = ((int)s.Value).ToString();
            _commit.Add(() => set((int)s.Value));
            valueLabel = lbl;
            return s;
        }

        UIElement WithLabel(Slider s, TextBlock l) => new StackPanel { Orientation = Orientation.Horizontal, Children = { s, l } };

        // ---------------------------------------------------------------- pestañas

        UIElement General()
        {
            var g = Form();
            Section(g, "Personalidad");
            Row(g, "Asistente", Choice(() => _s.Persona, v => _s.Persona = v, ("jarvis", "JARVIS (voz masculina, formal)"), ("viernes", "VIERNES (voz femenina, cercana)")));
            Row(g, "Cómo llamarle", Str(() => _s.Treatment, v => _s.Treatment = v), "Por ejemplo «señor», «señora», su nombre… Déjelo vacío para no usar tratamiento.");
            Row(g, "Palabra para despertarle", Str(() => _s.WakeWord, v => _s.WakeWord = v == "" ? (_s.IsViernes ? "Viernes" : "Jarvis") : v));
            Row(g, "Su ciudad", Str(() => _s.City, v => _s.City = v), "Para el tiempo y la hora local.");
            Section(g, "Funcionamiento");
            Row(g, "Atajo de teclado", Str(() => _s.Hotkey, v => _s.Hotkey = v), "Abre el panel para escribir o hablar. Ejemplos: Ctrl+Alt+J, Win+Shift+J, F9.");
            Row(g, "", Bool("Iniciar con Windows", () => _s.StartWithWindows, v => _s.StartWithWindows = v));
            Row(g, "", Bool("Saludar al iniciar", () => _s.GreetOnStart, v => _s.GreetOnStart = v));
            Row(g, "", Bool("Seguir escuchando tras responder (sin repetir el nombre)", () => _s.FollowUp, v => _s.FollowUp = v));
            Row(g, "Conversación: seguir escuchando", WithLabel(Range(3, 30, () => _s.FollowUpSeconds, v => _s.FollowUpSeconds = v, out var lf), lf),
                "Segundos que espera otra frase después de responder, sin que tenga que decir su nombre.");
            Row(g, "", Bool("Confirmar en voz alta lo que hago («Listo», «Pausado», «Abriendo…»)", () => _s.SpeakConfirmations, v => _s.SpeakConfirmations = v));
            Row(g, "", Bool("Poder interrumpirme llamándome por mi nombre mientras hablo", () => _s.BargeIn, v => _s.BargeIn = v));
            Row(g, "", Bool("Pedir confirmación para apagar, reiniciar o suspender", () => _s.ConfirmPower, v => _s.ConfirmPower = v));
            Row(g, "", Bool("Avisarme de batería baja, disco lleno o programas que no responden", () => _s.SystemAlerts, v => _s.SystemAlerts = v));
            Row(g, "Buscador", Choice(() => _s.SearchEngine, v => _s.SearchEngine = v, ("google", "Google"), ("bing", "Bing"), ("duckduckgo", "DuckDuckGo")));
            Row(g, "Paso del volumen", WithLabel(Range(1, 50, () => _s.VolumeStep, v => _s.VolumeStep = v, out var l1), l1));
            return g;
        }

        UIElement Voice()
        {
            var g = Form();
            Section(g, "Escuchar");
            Row(g, "", Bool("Escuchar por el micrófono", () => _s.VoiceInput, v => _s.VoiceInput = v));
            var langs = Jarvis.Speech.ModernListener.SpanishLanguages();
            Row(g, "Reconocedor", Choice(() => _s.Recognizer, v => _s.Recognizer = v,
                ("auto", "Automático (recomendado)"), ("moderno", "Windows moderno (dictado, el que mejor entiende)"), ("clasico", "Windows clásico (sin internet; con Whisper si está)")),
                langs.Length > 0 ? "Dictado en español disponible: " + string.Join(", ", langs) + ". El moderno necesita «Reconocimiento de voz en línea» activado en Privacidad › Voz."
                                 : "Este Windows no tiene dictado en español: añada «Español (México)» con reconocimiento de voz en Hora e idioma.");
            Row(g, "Idioma del reconocedor", Editable(() => _s.RecognizerLanguage, v => _s.RecognizerLanguage = v, langs), "Vacío = el mejor español disponible.");
            var diag = new Button { Content = "Diagnóstico de voz", Width = 160, HorizontalAlignment = HorizontalAlignment.Left };
            diag.Click += (o, e) => RunDiagnostics?.Invoke();
            Row(g, "", diag);
            Row(g, "Whisper (clásico)", Choice(() => _s.SpeechEngine, v => _s.SpeechEngine = v,
                ("whisper", "Repasar cada frase con Whisper (más preciso)"), ("windows", "No usar Whisper")),
                NeuralVoices.WhisperExe != "" ? "Whisper instalado: " + Path.GetFileName(NeuralVoices.WhisperModel) : "Whisper no está instalado: use «instalar-voces.bat» de la carpeta de JARVIS.");
            Row(g, "Modelo de Whisper", Choice(() => _s.WhisperModel, v => _s.WhisperModel = v,
                ("auto", "Automático (el mejor instalado)"), ("turbo", "Large v3 Turbo (el más preciso)"), ("small", "Small (equilibrado)"), ("base", "Base (el más rápido)")));
            Row(g, "Tecla para hablar", Str(() => _s.PushToTalkKey, v => _s.PushToTalkKey = v),
                "Manténgala pulsada mientras habla (sin decir «" + _s.WakeWord + "»). Ejemplos: F8, Ctrl+Espacio. Vacío = desactivada.");
            Row(g, "Pausa para terminar la frase", WithLabel(Range(3, 25, () => _s.EndSilenceMs / 100, v => _s.EndSilenceMs = v * 100, out var lp), lp),
                "En décimas de segundo. Súbala si le corta antes de acabar; bájela para que responda antes.");
            Row(g, "Sensibilidad", Choice(() => _s.Sensitivity, v => _s.Sensitivity = v, ("alta", "Alta (responde más, se equivoca más)"), ("normal", "Normal"), ("baja", "Baja (solo si está muy seguro)")));
            Row(g, "", Bool("No hablar en voz alta en presentaciones, juegos a pantalla completa o llamadas", () => _s.AutoQuiet, v => _s.AutoQuiet = v));
            Row(g, "", Bool("Bajar el volumen de la música y los vídeos mientras le escucho o hablo", () => _s.DuckAudio, v => _s.DuckAudio = v));
            Row(g, "Volumen de lo demás", WithLabel(Range(0, 90, () => _s.DuckLevel, v => _s.DuckLevel = v, out var ld), ld), "Porcentaje al que se baja (0 = silencio).");

            Section(g, "Hablar");
            Row(g, "", Bool("Responder en voz alta", () => _s.VoiceOutput, v => _s.VoiceOutput = v));
            Row(g, "Voz", Choice(() => _s.VoiceEngine, v => _s.VoiceEngine = v,
                ("cloud", "En la nube (la más natural: Gemini, OpenAI, ElevenLabs o Azure)"), ("neural", "Neuronal en el equipo (Piper, gratis)"), ("windows", "Voz de Windows")));
            var voices = Directory.Exists(Path.Combine(NeuralVoices.Dir, "voces"))
                ? Directory.GetFiles(Path.Combine(NeuralVoices.Dir, "voces"), "*.onnx").Select(f => Path.GetFileNameWithoutExtension(f)).ToList()
                : new List<string>();
            Row(g, "Voz neuronal", Editable(() => _s.PiperVoice, v => _s.PiperVoice = v, voices),
                voices.Count == 0 ? "No hay voces de Piper instaladas." : "Vacío = la mejor para " + (_s.IsViernes ? "VIERNES" : "JARVIS") + ". Instaladas: " + voices.Count + ".");
            Row(g, "Hablante (voces con varios)", WithLabel(Range(0, 3, () => _s.PiperSpeaker, v => _s.PiperSpeaker = v, out var l2), l2), "Sharvard: 0 = hombre, 1 = mujer.");
            Row(g, "Velocidad", WithLabel(Range(-10, 10, () => _s.VoiceRate, v => _s.VoiceRate = v, out var l3), l3));
            Row(g, "Voz de Windows", Editable(() => _s.WindowsVoice, v => _s.WindowsVoice = v, Speaker.WindowsVoices()), "Vacío = la primera en español.");

            Section(g, "Voz en la nube");
            Row(g, "Servicio", Choice(() => _s.CloudProvider, v => _s.CloudProvider = v, ("gemini", "Google Gemini (muy expresiva; usa la clave de Gemini)"), ("openai", "OpenAI (gpt-4o-mini-tts)"), ("elevenlabs", "ElevenLabs"),
                ("azure", "Azure Speech (voces colombianas; 500.000 caracteres gratis al mes)")),
                "Gemini usa la misma clave que puso para la IA de Gemini. Azure tiene un plan gratuito generoso con voces de Colombia.");
            Row(g, "Clave del servicio", Secret(() => _s.CloudKey, v => _s.CloudKey = v), "Con OpenAI o Gemini puede dejarla vacía si ya guardó la clave de ese servicio para la IA.");
            Row(g, "Voz", Str(() => _s.CloudVoice, v => _s.CloudVoice = v), "Vacío = Charon (Gemini), cedar (OpenAI), George (ElevenLabs) o es-CO-GonzaloNeural (Azure). Gemini también: Orus, Algenib, Gacrux; para VIERNES Kore, Aoede, Sulafat.");
            Row(g, "Región de Azure", Str(() => _s.CloudRegion, v => _s.CloudRegion = v), "Por ejemplo westeurope o eastus.");
            Row(g, "Modelo", Str(() => _s.CloudModel, v => _s.CloudModel = v));
            Row(g, "Estilo (OpenAI y Gemini)", Str(() => _s.CloudStyle, v => _s.CloudStyle = v), "Cómo debe sonar: tono, ritmo, acento. Ej.: «voz masculina grave y serena, acento colombiano neutro».");

            var test = new Button { Content = "Probar la voz", Width = 140, HorizontalAlignment = HorizontalAlignment.Left };
            test.Click += (o, e) =>
            {
                foreach (var a in _commit) a();
                TestVoice?.Invoke(_s, "Hola. Soy " + _s.Name + ". Así sueno con estos ajustes.");
            };
            Row(g, "", test);
            return g;
        }

        UIElement Intelligence()
        {
            var g = Form();
            Section(g, "Inteligencia artificial");
            // Proveedor y clave van juntos: al cambiar de proveedor aparece la clave que tenía guardada.
            var provider = new ComboBox();
            foreach (var (v, l) in new[]
                     {
                         ("anthropic", "Claude (Anthropic)"), ("gemini", "Gemini (Google)"), ("ollama", "Ollama (en este equipo: gratis y sin internet)"),
                         ("openai", "OpenAI o compatible (LM Studio, OpenRouter…)"),
                     })
                provider.Items.Add(new ComboBoxItem { Content = l, Tag = v });
            provider.SelectedItem = provider.Items.Cast<ComboBoxItem>().FirstOrDefault(i => (string)i.Tag == _s.AiProvider) ?? provider.Items[0];
            var key = new PasswordBox { Password = _s.ApiKey, Padding = new Thickness(3) };
            var keyHint = new TextBlock { Foreground = Brushes.Gray, FontSize = 11.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 0) };
            var keyRow = new StackPanel { Children = { key, keyHint } };
            var modelHint = new TextBlock { Foreground = Brushes.Gray, FontSize = 11.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 0) };
            var model = new ComboBox { IsEditable = true, Text = _s.Model };
            var url = new TextBox { Text = _s.ApiUrl, Padding = new Thickness(3) };
            var urlHint = new TextBlock { Foreground = Brushes.Gray, FontSize = 11.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 0) };
            var urlRow = new StackPanel { Children = { url, urlHint } };
            var find = new Button { Content = "Buscar modelos instalados", Padding = new Thickness(10, 3, 10, 3), HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 4, 0, 0) };
            var findResult = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0) };
            var modelRow = new StackPanel { Children = { model, modelHint, find, findResult } };
            string current = _s.AiProvider;
            UIElement keyLabel = null, urlLabel = null;
            bool LocalNow() => current == "ollama" || (current == "openai" && url.Text.Trim() != "");
            void Hints()
            {
                keyHint.Text = current switch
                {
                    "gemini" => "Consígala gratis en aistudio.google.com › Get API key. Se guarda solo en este equipo.",
                    "openai" => "De platform.openai.com › API keys (vacía si usa LM Studio u otro servidor propio). Se guarda solo en este equipo.",
                    _ => "De console.anthropic.com › API Keys. Se guarda solo en este equipo.",
                };
                modelHint.Text = current switch
                {
                    "gemini" => "Vacío = gemini-3.8-flash. Otros: gemini-3.5-flash-lite (más barato), gemini-4-argon (el más capaz).",
                    "ollama" => "Vacío = el primero que tenga instalado. Pulse «Buscar modelos instalados» para elegir. Recomendados en español: qwen3, gemma3, llama3.2.",
                    "openai" => url.Text.Trim() == "" ? "Vacío = gpt-5-mini." : "Vacío = el primero que ofrezca su servidor.",
                    _ => "Vacío = claude-haiku-5-5. Otros: claude-sonnet-5-5, claude-opus-5-5.",
                };
                urlHint.Text = current == "ollama"
                    ? "Vacío = http://localhost:11434 (Ollama en este equipo). Si está en otro equipo: http://192.168.1.20:11434"
                    : "Solo para servidores propios, p. ej. http://localhost:1234 (LM Studio). Vacío = OpenAI en internet.";
                keyRow.Visibility = current == "ollama" ? Visibility.Collapsed : Visibility.Visible;
                urlRow.Visibility = current == "ollama" || current == "openai" ? Visibility.Visible : Visibility.Collapsed;
                find.Visibility = LocalNow() ? Visibility.Visible : Visibility.Collapsed;
                if (keyLabel != null) keyLabel.Visibility = keyRow.Visibility;
                if (urlLabel != null) urlLabel.Visibility = urlRow.Visibility;
            }
            url.TextChanged += (o, e) => Hints();
            find.Click += async (o, e) =>
            {
                var tmp = new Settings { AiProvider = current, ApiUrl = url.Text.Trim(), ApiKey = key.Password.Trim() };
                findResult.Text = "Buscando en " + Jarvis.Ai.LocalAi.BaseUrl(tmp) + "…";
                find.IsEnabled = false;
                try
                {
                    var list = await Jarvis.Ai.LocalAi.ListModels(tmp);
                    model.Items.Clear();
                    foreach (var m in list) model.Items.Add(m);
                    if (list.Count == 0)
                        findResult.Text = "El servidor responde, pero no tiene modelos. En una consola escriba: ollama pull qwen3  (o llama3.2, más ligero).";
                    else
                    {
                        if (model.Text.Trim() == "") model.Text = list[0];
                        findResult.Text = "Correcto: " + list.Count + (list.Count == 1 ? " modelo instalado. " : " modelos instalados. ") + "Elíjalo en la lista de arriba.";
                        model.IsDropDownOpen = true;
                    }
                }
                catch (Exception ex)
                {
                    findResult.Text = (current == "ollama"
                        ? "No encuentro Ollama. Instálelo desde ollama.com, ábralo (debe verse su icono junto al reloj) y descargue un modelo: ollama pull qwen3. "
                        : "No encuentro el servidor. ") + "(" + ex.GetBaseException().Message + ")";
                }
                find.IsEnabled = true;
            };
            Hints();
            provider.SelectionChanged += (o, e) =>
            {
                string next = (string)((ComboBoxItem)provider.SelectedItem).Tag;
                if (next == current) return;
                _s.ApiKey = key.Password.Trim();
                _s.Model = model.Text.Trim();
                // SwitchAi parte del proveedor anterior: se fija antes de cambiar.
                _s.AiProvider = current;
                _s.SwitchAi(next);
                key.Password = _s.ApiKey;
                model.Items.Clear();
                model.Text = _s.Model;
                if (next == "ollama" && url.Text.Contains("api.openai.com")) url.Text = "";
                current = next;
                findResult.Text = "";
                Hints();
            };
            _commit.Add(() =>
            {
                _s.AiProvider = current;
                _s.ApiKey = current == "ollama" ? "" : key.Password.Trim();
                if (_s.ApiKey != "") _s.ApiKeys[current] = _s.ApiKey;
                else if (current != "ollama") _s.ApiKeys.Remove(current);
                _s.Model = model.Text.Trim();
                _s.ApiUrl = url.Text.Trim();
            });
            Row(g, "Proveedor", provider);
            Row(g, "Clave de la API", keyRow);
            keyLabel = g.Children[g.Children.Count - 2];
            Row(g, "Modelo", modelRow);
            Row(g, "Dirección del servidor", urlRow);
            urlLabel = g.Children[g.Children.Count - 2];
            Hints();
            Row(g, "", Bool("Contarle a la IA el título de la ventana activa", () => _s.SendContext, v => _s.SendContext = v));
            Row(g, "", Bool("Resolver primero en el equipo lo que sé hacer (más rápido y gratis)", () => _s.LocalFirst, v => _s.LocalFirst = v));
            Row(g, "", Bool("Empezar a hablar mientras la IA aún escribe", () => _s.StreamAi, v => _s.StreamAi = v));
            var result = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0) };
            var test = new Button { Content = "Probar la conexión", Width = 160, HorizontalAlignment = HorizontalAlignment.Left };
            test.Click += async (o, e) =>
            {
                foreach (var a in _commit) a();
                result.Text = "Probando…";
                test.IsEnabled = false;
                try { result.Text = TestAi != null ? await TestAi(_s) : "No disponible."; }
                catch (Exception ex) { result.Text = ex.Message; }
                test.IsEnabled = true;
            };
            Row(g, "", new StackPanel { Children = { test, result } });
            return g;
        }

        UIElement Agenda()
        {
            var g = Form();
            Section(g, "Calendario");
            var urls = new TextBox
            {
                Text = (_s.CalendarUrl ?? "").Replace(" ", Environment.NewLine),
                AcceptsReturn = true,
                TextWrapping = TextWrapping.Wrap,
                MinHeight = 70,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Padding = new Thickness(3),
            };
            _commit.Add(() => _s.CalendarUrl = string.Join(" ", urls.Text.Split(new[] { '\n', '\r', ' ' }, StringSplitOptions.RemoveEmptyEntries)));
            Row(g, "Enlaces iCal (uno por línea)", urls,
                "Google Calendar: Configuración › su calendario › «Dirección secreta en formato iCal». " +
                "Outlook: Calendario › Compartir › Publicar calendario › enlace ICS. Solo se lee; JARVIS no cambia nada de su agenda.");
            Row(g, "Avisar antes de cada evento", WithLabel(Range(0, 60, () => _s.CalendarAlertMinutes, v => _s.CalendarAlertMinutes = v, out var la), la), "Minutos (0 = sin avisos).");
            var result = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0) };
            var test = new Button { Content = "Probar los enlaces", Width = 160, HorizontalAlignment = HorizontalAlignment.Left };
            test.Click += async (o, e) =>
            {
                result.Text = "Descargando…";
                test.IsEnabled = false;
                int ok = 0, events = 0;
                var errors = new List<string>();
                foreach (var raw in urls.Text.Split(new[] { '\n', '\r', ' ' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    string u = raw.Trim().StartsWith("webcal", StringComparison.OrdinalIgnoreCase) ? "https" + raw.Trim().Substring(6) : raw.Trim();
                    try
                    {
                        using var http = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromSeconds(20) };
                        string ics = await http.GetStringAsync(u);
                        var list = await System.Threading.Tasks.Task.Run(() => Jarvis.Commands.ICal.Parse(ics, DateTime.Today, DateTime.Today.AddDays(30)));
                        ok++;
                        events += list.Count;
                    }
                    catch (Exception ex) { errors.Add(ex.Message); }
                }
                result.Text = ok == 0 && errors.Count == 0 ? "Pegue al menos un enlace."
                            : (ok > 0 ? "Correcto: " + events + " eventos en los próximos 30 días. " : "") + (errors.Count > 0 ? "Fallaron " + errors.Count + ": " + errors[0] : "");
                test.IsEnabled = true;
            };
            Row(g, "", new StackPanel { Children = { test, result } });
            Section(g, "Qué puede preguntar");
            Row(g, "", new TextBlock
            {
                TextWrapping = TextWrapping.Wrap,
                Text = "«¿Qué tengo hoy?», «¿qué tengo mañana?», «¿qué tengo el jueves?», «¿cuál es mi próxima reunión?», «¿qué tengo esta semana?», " +
                       "«resumen del día» o simplemente «buenos días».",
            });
            return g;
        }

        UIElement Integrations()
        {
            var g = Form();
            Section(g, "Avisos al celular (ntfy, gratis)");
            var topic = Str(() => _s.NtfyTopic, v => _s.NtfyTopic = v);
            Row(g, "Tema de ntfy", topic,
                "Instale la app «ntfy» en el teléfono (Android o iPhone), pulse + y suscríbase a un tema con un nombre difícil de adivinar " +
                "(por ejemplo jarvis-ana-7k2q9). Escriba aquí el mismo nombre. Luego diga «mándame al celular que compre pan».");
            Row(g, "Servidor (opcional)", Str(() => _s.NtfyServer, v => _s.NtfyServer = v), "Vacío = https://ntfy.sh");
            Row(g, "", Bool("Mandar también al celular los recordatorios, alarmas y avisos de agenda", () => _s.PhoneReminders, v => _s.PhoneReminders = v));
            var phoneResult = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0) };
            var phoneTest = new Button { Content = "Enviar una prueba", Width = 150, HorizontalAlignment = HorizontalAlignment.Left };
            phoneTest.Click += async (o, e) =>
            {
                foreach (var a in _commit) a();
                phoneResult.Text = "Enviando…";
                try
                {
                    string server = _s.NtfyServer.Trim() == "" ? "https://ntfy.sh" : _s.NtfyServer.Trim().TrimEnd('/');
                    using var http = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromSeconds(10) };
                    var res = await http.PostAsync(server + "/" + Uri.EscapeDataString(_s.NtfyTopic.Trim()),
                        new System.Net.Http.StringContent("Prueba de " + _s.Name + ": si lee esto, los avisos al celular funcionan.", System.Text.Encoding.UTF8, "text/plain"));
                    phoneResult.Text = res.IsSuccessStatusCode ? "Enviado. Mire el teléfono." : "El servidor respondió " + (int)res.StatusCode + ".";
                }
                catch (Exception ex) { phoneResult.Text = "No se pudo: " + ex.Message; }
            };
            Row(g, "", new StackPanel { Children = { phoneTest, phoneResult } });

            Section(g, "Control desde el celular (ntfy)");
            var remoteTopic = new TextBox { Text = _s.RemoteTopic, IsReadOnly = true, Padding = new Thickness(3), FontFamily = new FontFamily("Cascadia Mono, Consolas") };
            var remoteOn = new CheckBox { Content = "Recibir órdenes desde el celular", IsChecked = _s.RemoteControl, Margin = new Thickness(0, 4, 0, 4) };
            void EnsureTopic()
            {
                if (remoteTopic.Text.Trim().Length < 16 && NewTopic != null) remoteTopic.Text = NewTopic();
            }
            remoteOn.Checked += (o, e) => EnsureTopic();
            _commit.Add(() =>
            {
                _s.RemoteControl = remoteOn.IsChecked == true;
                if (_s.RemoteControl) EnsureTopic();
                _s.RemoteTopic = remoteTopic.Text.Trim();
            });
            Row(g, "", remoteOn,
                "Escríbale desde el teléfono «pon música», «¿qué tiempo hace?», «recuérdame a las 6 sacar la ropa» o «¿qué hay en mi pantalla?» y le contesta en el mismo canal. " +
                "Por seguridad, desde el celular no apaga ni reinicia el equipo, no cierra programas, no escribe en ventanas y no borra datos.");
            var topicButtons = new WrapPanel { Margin = new Thickness(0, 4, 0, 0) };
            Button Small(string text, Action a)
            {
                var b = new Button { Content = text, Padding = new Thickness(10, 3, 10, 3), Margin = new Thickness(0, 0, 8, 0) };
                b.Click += (o, e) => { try { a(); } catch (Exception ex) { MessageBox.Show(ex.Message, Title); } };
                return b;
            }
            string Server() => _s.NtfyServer.Trim() == "" ? "https://ntfy.sh" : _s.NtfyServer.Trim().TrimEnd('/');
            topicButtons.Children.Add(Small("Copiar el canal", () => { EnsureTopic(); Clipboard.SetText(remoteTopic.Text.Trim()); }));
            topicButtons.Children.Add(Small("Copiar el enlace", () => { EnsureTopic(); Clipboard.SetText(Server() + "/" + remoteTopic.Text.Trim()); }));
            topicButtons.Children.Add(Small("Canal nuevo", () =>
            {
                if (NewTopic == null) return;
                if (MessageBox.Show("El canal actual dejará de funcionar y tendrá que suscribirse al nuevo en el teléfono. ¿Seguir?", Title, MessageBoxButton.YesNo) == MessageBoxResult.Yes)
                    remoteTopic.Text = NewTopic();
            }));
            Row(g, "Canal secreto", new StackPanel { Children = { remoteTopic, topicButtons } },
                "En la app ntfy del teléfono: + › Suscribirse a un tema › escriba este nombre (mismo servidor que arriba). Quien no sepa el nombre no puede mandarle nada: " +
                "no lo comparta, y si cree que alguien lo sabe, pulse «Canal nuevo». También sirve el enlace en el navegador del teléfono.");

            Section(g, "Casa inteligente (Home Assistant)");
            Row(g, "Dirección", Str(() => _s.HaUrl, v => _s.HaUrl = v), "Por ejemplo http://homeassistant.local:8123 o http://192.168.1.50:8123");
            Row(g, "Token de acceso", Secret(() => _s.HaToken, v => _s.HaToken = v),
                "En Home Assistant: su perfil › Seguridad › Tokens de acceso de larga duración › Crear token. " +
                "Luego: «enciende la luz de la sala», «apaga todas las luces», «pon la luz del cuarto al 30», «activa la escena cine», «¿qué temperatura hay en casa?».");
            var haResult = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0) };
            var haTest = new Button { Content = "Probar la conexión", Width = 150, HorizontalAlignment = HorizontalAlignment.Left };
            haTest.Click += async (o, e) =>
            {
                foreach (var a in _commit) a();
                haResult.Text = "Conectando…";
                try
                {
                    using var http = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromSeconds(10) };
                    using var req = new System.Net.Http.HttpRequestMessage(System.Net.Http.HttpMethod.Get, _s.HaUrl.Trim().TrimEnd('/') + "/api/states");
                    req.Headers.Add("Authorization", "Bearer " + _s.HaToken.Trim());
                    using var res = await http.SendAsync(req);
                    if (!res.IsSuccessStatusCode) { haResult.Text = "Home Assistant respondió " + (int)res.StatusCode + (res.StatusCode == System.Net.HttpStatusCode.Unauthorized ? ": el token no es válido." : "."); return; }
                    using var doc = JsonDocument.Parse(await res.Content.ReadAsStringAsync());
                    var ids = doc.RootElement.EnumerateArray().Select(x => x.GetProperty("entity_id").GetString() ?? "").ToList();
                    int lights = ids.Count(i => i.StartsWith("light.")), switches = ids.Count(i => i.StartsWith("switch.")), scenes = ids.Count(i => i.StartsWith("scene."));
                    haResult.Text = "Conectado: " + lights + " luces, " + switches + " enchufes o interruptores, " + scenes + " escenas.";
                }
                catch (Exception ex) { haResult.Text = "No se pudo conectar: " + ex.GetBaseException().Message; }
            };
            Row(g, "", new StackPanel { Children = { haTest, haResult } });

            Section(g, "Resumen del día");
            Row(g, "Hora del resumen automático", Str(() => _s.BriefingTime, v => _s.BriefingTime = v),
                "Por ejemplo 07:30. A esa hora (o en cuanto se siente al equipo) le saluda con la hora, el tiempo, su agenda y sus avisos. Vacío = no.");

            Section(g, "YouTube");
            Row(g, "Clave de la API de YouTube (opcional)", Secret(() => _s.YouTubeApiKey, v => _s.YouTubeApiKey = v),
                "No hace falta: sin ella busca directamente en la página de YouTube. Con una clave gratuita de Google Cloud (API «YouTube Data v3») " +
                "la búsqueda es oficial y no se rompe si YouTube cambia su página.");

            Section(g, "Radio");
            Row(g, "País de las emisoras", Str(() => _s.RadioCountry, v => _s.RadioCountry = v),
                "Código de dos letras: CO (Colombia), MX, ES, AR… Luego: «pon la radio», «pon la emisora La Mega», «sintoniza Radio Tiempo».");
            return g;
        }

        UIElement Look()
        {
            var g = Form();
            Section(g, "Panel");
            Row(g, "Tema", Choice(() => _s.Theme, v => _s.Theme = v, ("azul", "Azul holográfico"), ("mark3", "Mark III (rojo y oro)"), ("verde", "Verde"), ("morado", "Morado"), ("grafito", "Grafito")));
            Row(g, "Posición", Choice(() => _s.Position, v => _s.Position = v, ("abajo-derecha", "Abajo a la derecha"), ("arriba-derecha", "Arriba a la derecha"), ("centro", "Arriba en el centro")));
            Row(g, "", Bool("Fondo de cristal (deja ver el escritorio desenfocado)", () => _s.Glass, v => _s.Glass = v));
            Row(g, "Opacidad del cristal", WithLabel(Range(20, 98, () => _s.GlassOpacity, v => _s.GlassOpacity = v, out var l1), l1));
            Row(g, "", Bool("Animación de arranque al aparecer", () => _s.BootAnimation, v => _s.BootAnimation = v));
            Row(g, "", Bool("Sonidos de aviso al escuchar y terminar", () => _s.UiSounds, v => _s.UiSounds = v));
            return g;
        }

        UIElement Protocols()
        {
            var p = new StackPanel();
            p.Children.Add(new TextBlock
            {
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 0, 0, 8),
                Text = "Una rutina es una frase suya que lanza varias órdenes. Escriba una por línea: la frase, dos puntos y los pasos separados por punto y coma. " +
                       "Un paso puede ser cualquier orden, «di …» para decir algo o «espera 5» para esperar segundos.\n" +
                       "Para que se lance sola, ponga entre corchetes cuándo: [07:30], [07:30 lun-vie], [21:00 sab,dom], [al iniciar] (al encender el equipo) " +
                       "o [al volver] (cuando vuelve al equipo tras 10 minutos o más sin usarlo). Con IA conectada, también puede pedírsela hablando.\n\nEjemplos:\n" +
                       "buenos días [07:30 lun-vie]: di Buenos días; qué tiempo hace; qué tengo hoy; noticias\n" +
                       "modo trabajo: abre Outlook; abre Teams; pon el volumen al 30; di A trabajar\n" +
                       "bienvenida [al volver]: di Bienvenido de nuevo; qué alarmas tengo",
            });
            var box = new TextBox
            {
                AcceptsReturn = true,
                TextWrapping = TextWrapping.NoWrap,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                MinHeight = 260,
                FontFamily = new FontFamily("Cascadia Mono, Consolas"),
                Text = string.Join(Environment.NewLine, _s.Protocols.Select(x => x.Phrase + (string.IsNullOrWhiteSpace(x.When) ? "" : " [" + x.When + "]") + ": " + string.Join("; ", x.Steps))),
            };
            _commit.Add(() =>
            {
                var list = new List<Protocol>();
                foreach (var raw in box.Text.Split('\n'))
                {
                    string line = raw.Trim();
                    int k = line.IndexOf(':');
                    if (k <= 0) continue;
                    // «frase [cuándo]: pasos» (los dos puntos de la hora van dentro de los corchetes)
                    int open = line.IndexOf('['), close = line.IndexOf(']');
                    string when = "";
                    string head;
                    if (open >= 0 && close > open && open < line.IndexOf(':', close))
                    {
                        when = line.Substring(open + 1, close - open - 1).Trim();
                        head = line.Substring(0, open).Trim();
                        k = line.IndexOf(':', close);
                    }
                    else head = line.Substring(0, k).Trim();
                    var steps = line.Substring(k + 1).Split(';').Select(x => x.Trim()).Where(x => x != "").ToList();
                    if (steps.Count == 0 || head == "") continue;
                    var sc = Jarvis.Commands.RoutinesModule.Parse(when);
                    list.Add(new Protocol { Phrase = head, Steps = steps, When = sc.Valid ? sc.ToString() : "" });
                }
                _s.Protocols = list;
            });
            p.Children.Add(box);
            return p;
        }

        UIElement MemoryTab()
        {
            var p = new StackPanel();
            p.Children.Add(new TextBlock
            {
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 0, 0, 8),
                Text = "Lo que " + _s.Name + " sabe de usted, un dato por línea. Lo aprende cuando se lo cuenta («mi hermana se llama Ana», «me gusta el vallenato», " +
                       "«las llaves están en el cajón») o cuando dice «recuerda que…». Puede corregir o borrar líneas aquí. Se guarda solo en este equipo.",
            });
            var box = new TextBox
            {
                AcceptsReturn = true,
                TextWrapping = TextWrapping.Wrap,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                MinHeight = 300,
                Text = string.Join(Environment.NewLine, Jarvis.Commands.Memory.All()),
            };
            string before = box.Text;
            _commit.Add(() =>
            {
                if (box.Text == before) return;
                Jarvis.Commands.Memory.Save(box.Text.Split('\n').Select(x => x.Trim()).Where(x => x != ""));
            });
            p.Children.Add(box);
            return p;
        }

        UIElement About()
        {
            var p = new StackPanel();
            void Add(string t, bool bold = false) => p.Children.Add(new TextBlock { Text = t, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 8), FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal });
            Add(_s.Title + " — asistente personal por voz para Windows.", true);
            Add("Diga «" + _s.WakeWord + "» y su orden, o pulse " + _s.Hotkey + " para escribir. Pruebe: «¿qué puedes hacer?».");
            Add("Voces: " + (NeuralVoices.WhisperExe != "" ? "Whisper instalado. " : "Whisper no instalado. ") + (NeuralVoices.PiperExe != "" ? "Piper instalado (" + NeuralVoices.VoiceStem + ")." : "Piper no instalado."));
            var row = new WrapPanel();
            Button B(string text, Action a)
            {
                var b = new Button { Content = text, Padding = new Thickness(10, 4, 10, 4), Margin = new Thickness(0, 0, 8, 8) };
                b.Click += (o, e) => { try { a(); } catch (Exception ex) { MessageBox.Show(ex.Message, "JARVIS"); } };
                return b;
            }
            if (RunFullCheck != null) row.Children.Add(B("Prueba completa", () => RunFullCheck()));
            if (CheckUpdates != null)
            {
                var upResult = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 8) };
                var auto = new CheckBox { Content = "Buscar versiones nuevas automáticamente (y avisarme)", IsChecked = _s.AutoUpdate, Margin = new Thickness(0, 4, 0, 4) };
                _commit.Add(() => _s.AutoUpdate = auto.IsChecked == true);
                Button install = null;
                install = B("Actualizar ahora", async () =>
                {
                    try { upResult.Text = await CheckUpdates(true); install.IsEnabled = false; }
                    catch (Exception ex) { upResult.Text = "No se pudo: " + ex.Message; }
                });
                install.Visibility = Visibility.Collapsed;
                var check = B("Buscar actualizaciones", async () =>
                {
                    upResult.Text = "Consultando GitHub…";
                    try
                    {
                        string r = await CheckUpdates(false);
                        upResult.Text = r;
                        install.Visibility = r.Contains("actualízate") ? Visibility.Visible : Visibility.Collapsed;
                    }
                    catch (Exception ex) { upResult.Text = "No se pudo: " + ex.Message; }
                });
                p.Children.Add(auto);
                p.Children.Add(new WrapPanel { Children = { check, install } });
                p.Children.Add(upResult);
            }
            row.Children.Add(B("Carpeta de ajustes y datos", () => Process.Start(new ProcessStartInfo(Settings.Folder) { UseShellExecute = true })));
            row.Children.Add(B("Ver el registro", () => Process.Start(new ProcessStartInfo(Path.Combine(Settings.Folder, "jarvis.log")) { UseShellExecute = true })));
            row.Children.Add(B("Carpeta de voces", () =>
            {
                Directory.CreateDirectory(NeuralVoices.Dir);
                Process.Start(new ProcessStartInfo(NeuralVoices.Dir) { UseShellExecute = true });
            }));
            string installer = Path.Combine(AppContext.BaseDirectory, "instalar-voces.bat");
            if (File.Exists(installer))
                row.Children.Add(B("Instalar voces neuronales", () => Process.Start(new ProcessStartInfo(installer) { UseShellExecute = true, WorkingDirectory = AppContext.BaseDirectory })));
            row.Children.Add(B("Reconocimiento de voz de Windows", () => Process.Start(new ProcessStartInfo("ms-settings:speech") { UseShellExecute = true })));
            p.Children.Add(row);
            return p;
        }
    }
}
