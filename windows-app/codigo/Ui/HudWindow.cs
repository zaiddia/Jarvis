using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;
using System.Windows.Threading;
using Jarvis.Core;

namespace Jarvis.Ui
{
    // El panel flotante: reactor, estado, lo que oyó, la respuesta y una caja para escribir.
    public sealed class HudWindow : Window
    {
        const double W = 480, Bevel = 18;
        const double GlassBleed = 14;   // el cristal se dibuja algo más grande para que el desenfoque no deje bordes vacíos
        readonly Grid _root = new Grid();
        // Las capas de fondo van en un Canvas: no cuentan al medir, así el panel solo crece con el texto.
        readonly Canvas _deco = new Canvas { IsHitTestVisible = false, ClipToBounds = false };
        readonly Image _glass = new Image { Stretch = Stretch.Fill, Effect = new BlurEffect { Radius = 12, KernelType = KernelType.Gaussian, RenderingBias = RenderingBias.Performance } };
        readonly Rectangle _tint = new Rectangle();
        readonly Rectangle _grid = new Rectangle { IsHitTestVisible = false };
        readonly Rectangle _scan = new Rectangle { Height = 2, IsHitTestVisible = false, Opacity = 0 };
        readonly Path _frame = new Path { IsHitTestVisible = false, StrokeThickness = 1.4 };
        readonly Path _corner = new Path { IsHitTestVisible = false, StrokeThickness = 3 };
        public readonly Reactor Reactor = new Reactor { Width = 132, Height = 132, Margin = new Thickness(14, 14, 6, 6), VerticalAlignment = VerticalAlignment.Top };
        readonly TextBlock _title = new TextBlock { FontSize = 19, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 16, 14, 0), TextTrimming = TextTrimming.CharacterEllipsis };
        readonly TextBlock _status = new TextBlock { FontSize = 11, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 2, 14, 8), TextTrimming = TextTrimming.CharacterEllipsis };
        // Lo que oyó: como mucho dos líneas, con «…» si es más largo.
        readonly TextBlock _heard = new TextBlock { FontSize = 12.5, FontStyle = FontStyles.Italic, TextWrapping = TextWrapping.Wrap, TextTrimming = TextTrimming.CharacterEllipsis, MaxHeight = 36, Margin = new Thickness(0, 0, 16, 6) };
        readonly TextBlock _reply = new TextBlock { FontSize = 14.5, TextWrapping = TextWrapping.Wrap, LineHeight = 20, Margin = new Thickness(0, 0, 8, 0) };
        readonly ScrollViewer _scroll = new ScrollViewer { VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, MaxHeight = 200, Margin = new Thickness(0, 0, 8, 10) };
        public readonly TextBox Input = new TextBox { FontSize = 13.5, BorderThickness = new Thickness(0, 0, 0, 1), Background = Brushes.Transparent, Padding = new Thickness(2, 6, 2, 6) };
        readonly TextBlock _placeholder = new TextBlock { FontSize = 13.5, IsHitTestVisible = false, Margin = new Thickness(4, 6, 0, 0), Text = "Escriba una orden o pregunta…" };
        readonly DispatcherTimer _hideTimer = new DispatcherTimer();
        readonly DispatcherTimer _glassTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.2) };
        Settings _s;
        Theme _t;
        HudState _state = HudState.Idle;
        IntPtr _hwnd;
        bool _shownOnce;
        bool _dragged;            // el usuario lo movió: se respeta su sitio (dentro de la pantalla)
        Rect _area;               // zona útil del monitor donde está el panel, en unidades WPF

        public event Action<string> Submitted;
        public event Action Dismissed;
        public event Action MicToggleRequested;
        public event Action SettingsRequested;
        public event Action QuitRequested;

        // ---- botones de la cabecera y control de volumen
        const string GMic = "\uE720", GMicOff = "\uEC54", GVol = "\uE767", GMute = "\uE74F", GSet = "\uE713", GHide = "\uE921", GClose = "\uE8BB";
        readonly StackPanel _buttons = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 10, 10, 0) };
        readonly HudButton _micBtn = new HudButton(GMic, "Escuchar: activado (clic para desactivar)");
        readonly HudButton _volBtn = new HudButton(GVol, "Volumen (clic para ajustar; rueda del ratón para subir o bajar)");
        readonly HudButton _setBtn = new HudButton(GSet, "Ajustes");
        readonly HudButton _hideBtn = new HudButton(GHide, "Ocultar el panel (Esc)");
        readonly HudButton _closeBtn = new HudButton(GClose, "Cerrar JARVIS") { Danger = true };
        readonly Grid _volRow = new Grid { Visibility = Visibility.Collapsed, Margin = new Thickness(0, 0, 14, 6) };
        readonly HudButton _muteBtn = new HudButton(GVol, "Silenciar o quitar el silencio");
        readonly VolumeBar _volBar = new VolumeBar { Height = 24, Margin = new Thickness(6, 0, 6, 0) };
        readonly TextBlock _volText = new TextBlock { FontSize = 12, VerticalAlignment = VerticalAlignment.Center, TextAlignment = TextAlignment.Right };
        readonly DispatcherTimer _volTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(700) };
        readonly DispatcherTimer _closeTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(3) };
        bool _closeArmed, _micOn = true;

        public HudWindow(Settings s)
        {
            Title = "JARVIS";
            Width = W;
            SizeToContent = SizeToContent.Height;
            MinHeight = 180;
            WindowStyle = WindowStyle.None;
            AllowsTransparency = true;
            Background = Brushes.Transparent;
            ResizeMode = ResizeMode.NoResize;
            Topmost = true;
            ShowInTaskbar = false;
            ShowActivated = false;
            FontFamily = new FontFamily("Bahnschrift, Segoe UI Variable Text, Segoe UI");
            UseLayoutRounding = true;

            var content = new Grid();
            content.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            content.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            content.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            content.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            content.Children.Add(Reactor);
            var right = new Grid();
            for (int i = 0; i < 4; i++) right.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            right.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            Grid.SetColumn(right, 1);
            // Cabecera: título y botones (micrófono, volumen, ajustes, ocultar, cerrar).
            var header = new Grid();
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            header.Children.Add(_title);
            _buttons.Children.Add(_micBtn);
            _buttons.Children.Add(_volBtn);
            _buttons.Children.Add(_setBtn);
            _buttons.Children.Add(_hideBtn);
            _buttons.Children.Add(_closeBtn);
            Grid.SetColumn(_buttons, 1);
            header.Children.Add(_buttons);
            right.Children.Add(header);
            Grid.SetRow(_status, 1);
            right.Children.Add(_status);
            // Fila del volumen (se despliega con el botón del altavoz).
            _volRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            _volRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            _volRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(44) });
            _volRow.Children.Add(_muteBtn);
            Grid.SetColumn(_volBar, 1);
            _volRow.Children.Add(_volBar);
            Grid.SetColumn(_volText, 2);
            _volRow.Children.Add(_volText);
            Grid.SetRow(_volRow, 2);
            right.Children.Add(_volRow);
            Grid.SetRow(_heard, 3);
            right.Children.Add(_heard);
            _scroll.Content = _reply;
            Grid.SetRow(_scroll, 4);
            right.Children.Add(_scroll);
            content.Children.Add(right);
            var inputBox = new Grid { Margin = new Thickness(16, 0, 16, 14) };
            inputBox.Children.Add(Input);
            inputBox.Children.Add(_placeholder);
            Grid.SetRow(inputBox, 1);
            Grid.SetColumnSpan(inputBox, 2);
            content.Children.Add(inputBox);

            _deco.Children.Add(_glass);
            _deco.Children.Add(_tint);
            _deco.Children.Add(_grid);
            _deco.Children.Add(_scan);
            var frames = new Canvas { IsHitTestVisible = false };
            frames.Children.Add(_frame);
            frames.Children.Add(_corner);
            _root.Children.Add(_deco);
            _root.Children.Add(content);
            _root.Children.Add(frames);
            Content = _root;

            _micBtn.Click += () => MicToggleRequested?.Invoke();
            _setBtn.Click += () => SettingsRequested?.Invoke();
            _hideBtn.Click += () =>
            {
                HideHud();
                Dismissed?.Invoke();
            };
            _closeBtn.Click += () =>
            {
                // Dos clics: el primero pide confirmación (evita cerrarlo sin querer).
                if (_closeArmed)
                {
                    _closeTimer.Stop();
                    _closeArmed = false;
                    QuitRequested?.Invoke();
                    return;
                }
                _closeArmed = true;
                _closeBtn.Armed = true;
                _status.Text = "●  ¿CERRAR " + _s.Name + "? PULSE ✕ OTRA VEZ";
                _status.Foreground = new SolidColorBrush(Theme.C(0xFF, 0x3B, 0x4E));
                _closeTimer.Start();
            };
            _closeTimer.Tick += (o, e) =>
            {
                _closeTimer.Stop();
                _closeArmed = false;
                _closeBtn.Armed = false;
                SetState(_state);
            };
            _volBtn.Click += () => ToggleVolume();
            _volBtn.MouseWheel += (o, e) =>
            {
                if (_volRow.Visibility != Visibility.Visible) ToggleVolume();
                NudgeVolume(e.Delta > 0 ? 0.05f : -0.05f);
                e.Handled = true;
            };
            _volRow.MouseWheel += (o, e) =>
            {
                NudgeVolume(e.Delta > 0 ? 0.05f : -0.05f);
                e.Handled = true;
            };
            _muteBtn.Click += () =>
            {
                bool muted = Jarvis.Speech.AudioDevices.GetMute() == true;
                Jarvis.Speech.AudioDevices.SetMute(!muted);
                ReadVolume();
            };
            _volBar.ValueChanged += v =>
            {
                Jarvis.Speech.AudioDevices.SetVolume(v);
                ShowVolume(v, false);
            };
            _volTimer.Tick += (o, e) => { if (!_volBar.Dragging) ReadVolume(); };

            Input.TextChanged += (o, e) => _placeholder.Visibility = Input.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
            Input.KeyDown += (o, e) =>
            {
                if (e.Key == Key.Enter && Input.Text.Trim() != "")
                {
                    string t = Input.Text.Trim();
                    Input.Clear();
                    Submitted?.Invoke(t);
                    e.Handled = true;
                }
            };
            PreviewKeyDown += (o, e) =>
            {
                if (e.Key == Key.Escape)
                {
                    HideHud();
                    Dismissed?.Invoke();
                    e.Handled = true;
                }
            };
            Input.GotKeyboardFocus += (o, e) => _hideTimer.Stop();
            MouseEnter += (o, e) => _hideTimer.Stop();
            MouseLeave += (o, e) => { if (!Input.IsKeyboardFocused && _state == HudState.Idle) HideLater(6); };
            MouseLeftButtonDown += (o, e) =>
            {
                if (Input.IsMouseOver || _scroll.IsMouseOver && _reply.ActualHeight > _scroll.ActualHeight) return;
                try
                {
                    var before = new Point(Left, Top);
                    DragMove();
                    if (Math.Abs(Left - before.X) + Math.Abs(Top - before.Y) > 4)
                    {
                        _dragged = true;
                        KeepInside(ActualHeight);
                        Store.Set("panel-pos", new[] { Left, Top });
                    }
                }
                catch { }
            };
            SizeChanged += (o, e) =>
            {
                Reshape();
                // Si crece por abajo (o arriba), se recoloca para no salirse de la pantalla.
                if (IsVisible) KeepInside(e.PreviousSize.Height);
            };
            _hideTimer.Tick += (o, e) =>
            {
                _hideTimer.Stop();
                if (IsMouseOver || Input.IsKeyboardFocused) return;
                HideHud();
            };
            _glassTimer.Tick += (o, e) => RefreshGlass();
            SourceInitialized += (o, e) =>
            {
                _hwnd = new WindowInteropHelper(this).Handle;
                // El panel no sale en sus propias capturas (así el cristal muestra lo de detrás).
                Native.SetWindowDisplayAffinity(_hwnd, Native.WDA_EXCLUDEFROMCAPTURE);
            };
            Apply(s);
        }

        public void Apply(Settings s)
        {
            _s = s;
            _t = Theme.Get(s.Theme);
            Reactor.SetTheme(_t);
            _title.Text = s.Title;
            _title.Foreground = new SolidColorBrush(_t.Text);
            _heard.Foreground = new SolidColorBrush(_t.Dim);
            _reply.Foreground = new SolidColorBrush(_t.Text);
            Input.Foreground = new SolidColorBrush(_t.Text);
            Input.CaretBrush = new SolidColorBrush(_t.Accent);
            Input.BorderBrush = new SolidColorBrush(Theme.WithAlpha(_t.Accent, 0.45));
            _placeholder.Foreground = new SolidColorBrush(Theme.WithAlpha(_t.Dim, 0.7));
            foreach (var b in new[] { _micBtn, _volBtn, _setBtn, _hideBtn, _closeBtn, _muteBtn }) b.SetColors(_t.Dim, _t.Text, _t.Accent);
            _volBar.SetColors(_t.Accent, _t.Dim);
            _volText.Foreground = new SolidColorBrush(_t.Dim);
            _closeBtn.ToolTip = "Cerrar " + s.Name;
            SetMic(_micOn);
            _scan.Fill = new LinearGradientBrush(new GradientStopCollection
            {
                new GradientStop(Theme.WithAlpha(_t.Accent, 0), 0),
                new GradientStop(Theme.WithAlpha(_t.Accent2, 0.9), 0.5),
                new GradientStop(Theme.WithAlpha(_t.Accent, 0), 1),
            }, 0);
            _grid.Fill = HexBrush(_t.Accent);
            SetState(_state);
            UpdateGlassMode();
            if (_shownOnce) _dragged = false;   // cambiar los ajustes devuelve el panel a su sitio
            Reshape();
        }

        void UpdateGlassMode()
        {
            double op = _s.Glass ? _s.GlassOpacity / 100.0 : 0.96;
            _tint.Fill = new LinearGradientBrush(Theme.WithAlpha(_t.Back, op), Theme.WithAlpha(Theme.Mix(_t.Back, _t.Accent, 0.12), op), 90);
            _glass.Visibility = _s.Glass ? Visibility.Visible : Visibility.Collapsed;
            if (!_s.Glass) _glass.Source = null;
        }

        // Rejilla hexagonal muy tenue.
        static Brush HexBrush(Color c)
        {
            var g = new StreamGeometry();
            using (var ctx = g.Open())
            {
                double r = 9, h = Math.Sqrt(3) * r;
                for (int k = 0; k < 2; k++)
                {
                    double ox = k * 1.5 * r, oy = k * h / 2;
                    ctx.BeginFigure(new Point(ox + r, oy), false, true);
                    for (int i = 1; i < 6; i++)
                    {
                        double a = i * Math.PI / 3;
                        ctx.LineTo(new Point(ox + Math.Cos(a) * r, oy + Math.Sin(a) * r), true, false);
                    }
                }
            }
            var d = new GeometryDrawing(null, new Pen(new SolidColorBrush(Theme.WithAlpha(c, 0.06)), 0.8), g);
            return new DrawingBrush(d)
            {
                TileMode = TileMode.Tile,
                Viewport = new Rect(0, 0, 27, 31.2),
                ViewportUnits = BrushMappingMode.Absolute,
                Viewbox = new Rect(-9, -15.6, 27, 31.2),
                ViewboxUnits = BrushMappingMode.Absolute,
                Stretch = Stretch.None,
            };
        }

        // Esquinas biseladas: la ventana tiene forma de placa de armadura.
        void Reshape()
        {
            double w = ActualWidth > 0 ? ActualWidth : W, h = ActualHeight > 0 ? ActualHeight : 220;
            var shape = new PathGeometry(new[]
            {
                new PathFigure(new Point(Bevel, 0), new PathSegment[]
                {
                    new LineSegment(new Point(w - 4, 0), true), new LineSegment(new Point(w, 4), true),
                    new LineSegment(new Point(w, h - Bevel), true), new LineSegment(new Point(w - Bevel, h), true),
                    new LineSegment(new Point(4, h), true), new LineSegment(new Point(0, h - 4), true),
                    new LineSegment(new Point(0, Bevel), true),
                }, true),
            });
            _root.Clip = shape;
            _tint.Width = w;
            _tint.Height = h;
            _grid.Width = w;
            _grid.Height = h;
            _scan.Width = w;
            _glass.Width = w + GlassBleed * 2;
            _glass.Height = h + GlassBleed * 2;
            Canvas.SetLeft(_glass, -GlassBleed);
            Canvas.SetTop(_glass, -GlassBleed);
            var inner = shape.Clone();
            inner.Transform = new ScaleTransform((w - 1.4) / w, (h - 1.4) / h, w / 2, h / 2);
            _frame.Data = inner;
            _frame.Stroke = new SolidColorBrush(Theme.WithAlpha(_t.For(_state), 0.55));
            var corner = new PathGeometry();
            corner.Figures.Add(new PathFigure(new Point(1.5, Bevel + 26), new[] { new LineSegment(new Point(1.5, Bevel), true), new LineSegment(new Point(Bevel, 1.5), true), new LineSegment(new Point(Bevel + 40, 1.5), true) }, false));
            corner.Figures.Add(new PathFigure(new Point(w - 1.5, h - Bevel - 26), new[] { new LineSegment(new Point(w - 1.5, h - Bevel), true), new LineSegment(new Point(w - Bevel, h - 1.5), true), new LineSegment(new Point(w - Bevel - 40, h - 1.5), true) }, false));
            _corner.Data = corner;
            _corner.Stroke = new SolidColorBrush(_t.For(_state));
        }

        public void SetState(HudState s)
        {
            _state = s;
            var col = _t.For(s);
            Reactor.SetState(s);
            _status.Text = "●  " + Theme.Label(s, _s.IsViernes);
            _status.Foreground = new SolidColorBrush(col);
            if (_frame.Data != null)
            {
                _frame.Stroke = new SolidColorBrush(Theme.WithAlpha(col, 0.55));
                _corner.Stroke = new SolidColorBrush(col);
            }
            if (s != HudState.Idle) _hideTimer.Stop();
        }

        public void SetHeard(string text) => _heard.Text = string.IsNullOrWhiteSpace(text) ? "" : "«" + text.Trim() + "»";

        public void SetReply(string text)
        {
            _reply.Text = text ?? "";
            _scroll.ScrollToTop();
        }

        public void AppendReply(string text)
        {
            if (string.IsNullOrEmpty(text)) return;
            _reply.Text = _reply.Text == "" ? text : _reply.Text.TrimEnd() + " " + text;
            _scroll.ScrollToEnd();
        }

        public void SetLevel(double v) => Reactor.SetLevel(v);

        // ---------------------------------------------------------------- botones

        public void SetMic(bool on)
        {
            _micOn = on;
            _micBtn.SetGlyph(on ? GMic : GMicOff);
            _micBtn.Active = !on;
            _micBtn.ToolTip = on ? "Escuchar: activado (clic para desactivar)" : "Escuchar: desactivado (clic para activar)";
        }

        void ToggleVolume()
        {
            bool show = _volRow.Visibility != Visibility.Visible;
            _volRow.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
            _volBtn.Active = show;
            if (show)
            {
                ReadVolume();
                _volTimer.Start();
            }
            else _volTimer.Stop();
            FitHeight();
        }

        void NudgeVolume(float d)
        {
            float v = Jarvis.Speech.AudioDevices.GetVolume();
            if (v < 0) return;
            v = Math.Clamp(v + d, 0f, 1f);
            Jarvis.Speech.AudioDevices.SetVolume(v);
            ShowVolume(v, false);
        }

        void ReadVolume()
        {
            float v = Jarvis.Speech.AudioDevices.GetVolume();
            bool muted = Jarvis.Speech.AudioDevices.GetMute() == true;
            if (v < 0)
            {
                _volText.Text = "—";
                return;
            }
            ShowVolume(v, muted);
        }

        void ShowVolume(float v, bool muted)
        {
            _volBar.Display(v, muted);
            _volText.Text = muted ? "mudo" : (int)Math.Round(v * 100) + " %";
            string g = muted || v <= 0.001f ? GMute : GVol;
            _muteBtn.SetGlyph(g);
            _volBtn.SetGlyph(g);
        }

        // ---------------------------------------------------------------- mostrar y ocultar

        // Zona útil (sin barra de tareas) del monitor del panel, en unidades WPF.
        Rect WorkArea()
        {
            try
            {
                var screen = _hwnd != IntPtr.Zero ? System.Windows.Forms.Screen.FromHandle(_hwnd) : System.Windows.Forms.Screen.FromPoint(System.Windows.Forms.Cursor.Position);
                var wa = screen.WorkingArea;
                var src = PresentationSource.FromVisual(this);
                var m = src?.CompositionTarget?.TransformFromDevice ?? Matrix.Identity;
                var tl = m.Transform(new Point(wa.Left, wa.Top));
                var br = m.Transform(new Point(wa.Right, wa.Bottom));
                return new Rect(tl, br);
            }
            catch
            {
                return SystemParameters.WorkArea;
            }
        }

        // Alto máximo: nunca más del 70 % de la pantalla; la respuesta larga se desplaza.
        void FitHeight()
        {
            _area = WorkArea();
            double max = Math.Max(220, Math.Min(520, _area.Height * 0.7));
            MaxHeight = max;
            // reactor/título/estado/oído + caja de texto ocupan unos 175
            _scroll.MaxHeight = Math.Max(60, max - 175 - (_volRow.Visibility == Visibility.Visible ? 30 : 0));
        }

        void Place()
        {
            FitHeight();
            var wa = _area;
            double h = ActualHeight > 0 ? ActualHeight : 230;
            if (_dragged || (!_shownOnce && TryRestore())) { KeepInside(h); return; }
            switch (_s.Position)
            {
                case "arriba-derecha":
                    Left = wa.Right - W - 22;
                    Top = wa.Top + 22;
                    break;
                case "centro":
                    Left = wa.Left + (wa.Width - W) / 2;
                    Top = wa.Top + 60;
                    break;
                default:
                    Left = wa.Right - W - 22;
                    Top = wa.Bottom - h - 22;
                    break;
            }
        }

        bool TryRestore()
        {
            var p = Store.Get<double[]>("panel-pos", null);
            if (p == null || p.Length != 2) return false;
            Left = p[0];
            Top = p[1];
            _dragged = true;
            return true;
        }

        // Mantiene el panel dentro de la pantalla. Abajo: crece hacia arriba. Arriba: hacia abajo.
        void KeepInside(double previousHeight)
        {
            if (_area.Width <= 0) _area = WorkArea();
            var wa = _area;
            double h = ActualHeight, w = ActualWidth > 0 ? ActualWidth : W;
            bool bottomAnchored = !_dragged ? (_s.Position != "arriba-derecha" && _s.Position != "centro") : Top + previousHeight / 2 > wa.Top + wa.Height / 2;
            if (bottomAnchored && previousHeight > 0 && Math.Abs(h - previousHeight) > 0.5)
                Top -= h - previousHeight;
            const double m = 8;
            if (Top + h > wa.Bottom - m) Top = wa.Bottom - m - h;
            if (Top < wa.Top + m) Top = wa.Top + m;
            if (Left + w > wa.Right - m) Left = wa.Right - m - w;
            if (Left < wa.Left + m) Left = wa.Left + m;
        }

        public void ShowHud(bool activate)
        {
            _hideTimer.Stop();
            bool wasHidden = !IsVisible;
            if (wasHidden)
            {
                Opacity = 0;
                if (!_shownOnce) Place();
                Show();
                Place();
                _shownOnce = true;
                RefreshGlass();
                Reactor.Start();
                if (_s.Glass) _glassTimer.Start();
                Boot();
            }
            if (activate)
            {
                Activate();
                Input.Focus();
            }
        }

        void Boot()
        {
            var fade = new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(_s.BootAnimation ? 260 : 90)) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } };
            BeginAnimation(OpacityProperty, fade);
            if (!_s.BootAnimation) return;
            var tt = new TranslateTransform();
            _scan.RenderTransform = tt;
            double h = ActualHeight > 0 ? ActualHeight : 220;
            _scan.BeginAnimation(OpacityProperty, new DoubleAnimationUsingKeyFrames
            {
                KeyFrames = { new LinearDoubleKeyFrame(0.9, KeyTime.FromPercent(0.1)), new LinearDoubleKeyFrame(0.9, KeyTime.FromPercent(0.8)), new LinearDoubleKeyFrame(0, KeyTime.FromPercent(1)) },
                Duration = TimeSpan.FromMilliseconds(620),
            });
            tt.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(0, h - 2, TimeSpan.FromMilliseconds(620)) { EasingFunction = new QuadraticEase() });
            var st = new ScaleTransform(0.6, 0.6, 66, 66);
            Reactor.RenderTransform = st;
            var grow = new DoubleAnimation(0.6, 1, TimeSpan.FromMilliseconds(420)) { EasingFunction = new BackEase { Amplitude = 0.35, EasingMode = EasingMode.EaseOut } };
            st.BeginAnimation(ScaleTransform.ScaleXProperty, grow);
            st.BeginAnimation(ScaleTransform.ScaleYProperty, grow);
        }

        public void HideLater(double seconds)
        {
            _hideTimer.Stop();
            _hideTimer.Interval = TimeSpan.FromSeconds(seconds);
            _hideTimer.Start();
        }

        public void HideHud()
        {
            _hideTimer.Stop();
            _volTimer.Stop();
            _volRow.Visibility = Visibility.Collapsed;
            _volBtn.Active = false;
            _glassTimer.Stop();
            if (!IsVisible) return;
            var fade = new DoubleAnimation(Opacity, 0, TimeSpan.FromMilliseconds(180));
            fade.Completed += (o, e) =>
            {
                if (Opacity > 0.05) return;
                Hide();
                Reactor.Stop();
                BeginAnimation(OpacityProperty, null);
                Opacity = 0;
            };
            BeginAnimation(OpacityProperty, fade);
        }

        public bool Busy => IsVisible && (IsMouseOver || Input.IsKeyboardFocused || Input.Text.Length > 0);

        // ---------------------------------------------------------------- cristal: lo de detrás, desenfocado

        [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
        [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);
        [StructLayout(LayoutKind.Sequential)] struct RECT { public int L, T, R, B; }

        void RefreshGlass()
        {
            if (!_s.Glass || _hwnd == IntPtr.Zero || !IsVisible) return;
            try
            {
                if (!GetWindowRect(_hwnd, out var r) || r.R - r.L < 10 || r.B - r.T < 10) return;
                var dpi = VisualTreeHelper.GetDpi(this);
                int bleedX = (int)Math.Round(GlassBleed * dpi.DpiScaleX), bleedY = (int)Math.Round(GlassBleed * dpi.DpiScaleY);
                r.L -= bleedX; r.T -= bleedY; r.R += bleedX; r.B += bleedY;
                int w = r.R - r.L, h = r.B - r.T;
                using var bmp = new System.Drawing.Bitmap(w / 3 + 1, h / 3 + 1);
                using (var full = new System.Drawing.Bitmap(w, h))
                {
                    using (var g = System.Drawing.Graphics.FromImage(full)) g.CopyFromScreen(r.L, r.T, 0, 0, new System.Drawing.Size(w, h));
                    using var g2 = System.Drawing.Graphics.FromImage(bmp);
                    g2.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.Bilinear;
                    g2.DrawImage(full, 0, 0, bmp.Width, bmp.Height);
                }
                IntPtr hb = bmp.GetHbitmap();
                try
                {
                    var src = Imaging.CreateBitmapSourceFromHBitmap(hb, IntPtr.Zero, Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
                    src.Freeze();
                    _glass.Source = src;
                }
                finally { DeleteObject(hb); }
            }
            catch (Exception e)
            {
                Log.Write("Cristal: " + e.Message);
                _glassTimer.Stop();
            }
        }

        protected override void OnLocationChanged(EventArgs e)
        {
            base.OnLocationChanged(e);
            if (IsVisible && _s != null && _s.Glass) RefreshGlass();
            if (IsVisible && _hwnd != IntPtr.Zero)
            {
                var a = WorkArea();
                if (a != _area) FitHeight();   // pasó a otro monitor
            }
        }
    }

    // Botón pequeño de la cabecera con un icono de Segoe (sin el aspecto de botón de Windows).
    public sealed class HudButton : Border
    {
        readonly TextBlock _glyph = new TextBlock
        {
            FontFamily = new FontFamily("Segoe Fluent Icons, Segoe MDL2 Assets"),
            FontSize = 12,
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
        };
        Color _fg = Colors.LightGray, _hover = Colors.White, _accent = Colors.DeepSkyBlue;
        bool _active, _armed, _pressed;
        public bool Danger;
        public event Action Click;

        public HudButton(string glyph, string tip)
        {
            Width = 26;
            Height = 24;
            Margin = new Thickness(1, 0, 1, 0);
            CornerRadius = new CornerRadius(3);
            Background = Brushes.Transparent;
            BorderThickness = new Thickness(1);
            BorderBrush = Brushes.Transparent;
            Cursor = Cursors.Hand;
            ToolTip = tip;
            _glyph.Text = glyph;
            Child = _glyph;
            MouseEnter += (o, e) => Paint();
            MouseLeave += (o, e) => { _pressed = false; Paint(); };
            MouseLeftButtonDown += (o, e) =>
            {
                _pressed = true;
                e.Handled = true;   // que no arrastre la ventana
                Paint();
            };
            MouseLeftButtonUp += (o, e) =>
            {
                bool fire = _pressed && IsMouseOver;
                _pressed = false;
                e.Handled = true;
                Paint();
                if (fire) Click?.Invoke();
            };
        }

        public void SetGlyph(string g) => _glyph.Text = g;

        public void SetColors(Color fg, Color hover, Color accent)
        {
            _fg = fg;
            _hover = hover;
            _accent = accent;
            Paint();
        }

        public bool Active { get => _active; set { _active = value; Paint(); } }
        public bool Armed { get => _armed; set { _armed = value; Paint(); } }

        void Paint()
        {
            var red = Theme.C(0xFF, 0x3B, 0x4E);
            bool over = IsMouseOver;
            Color fg = _armed ? Colors.White : over ? (Danger ? red : _hover) : _active ? _accent : _fg;
            if (_armed) Background = new SolidColorBrush(red);
            else if (over) Background = new SolidColorBrush(Theme.WithAlpha(Danger ? red : _accent, _pressed ? 0.35 : 0.18));
            else Background = Brushes.Transparent;
            BorderBrush = _active && !over ? new SolidColorBrush(Theme.WithAlpha(_accent, 0.5)) : Brushes.Transparent;
            _glyph.Foreground = new SolidColorBrush(fg);
        }
    }

    // Barra de volumen: se arrastra o se usa la rueda del ratón.
    public sealed class VolumeBar : FrameworkElement
    {
        double _value;
        bool _muted;
        Color _accent = Colors.DeepSkyBlue, _dim = Colors.Gray;
        public bool Dragging { get; private set; }
        public event Action<float> ValueChanged;

        public VolumeBar()
        {
            Cursor = Cursors.Hand;
            MouseLeftButtonDown += (o, e) =>
            {
                Dragging = true;
                CaptureMouse();
                FromMouse(e.GetPosition(this).X);
                e.Handled = true;
            };
            MouseMove += (o, e) => { if (Dragging) FromMouse(e.GetPosition(this).X); };
            MouseLeftButtonUp += (o, e) =>
            {
                Dragging = false;
                ReleaseMouseCapture();
                e.Handled = true;
            };
            LostMouseCapture += (o, e) => Dragging = false;
        }

        public void SetColors(Color accent, Color dim)
        {
            _accent = accent;
            _dim = dim;
            InvalidateVisual();
        }

        public void Display(double v, bool muted)
        {
            _value = Math.Clamp(v, 0, 1);
            _muted = muted;
            InvalidateVisual();
        }

        void FromMouse(double x)
        {
            double pad = 7, w = Math.Max(1, ActualWidth - pad * 2);
            _value = Math.Clamp((x - pad) / w, 0, 1);
            _muted = false;
            InvalidateVisual();
            ValueChanged?.Invoke((float)_value);
        }

        protected override void OnRender(DrawingContext dc)
        {
            double pad = 7, w = ActualWidth - pad * 2, y = ActualHeight / 2;
            if (w <= 0) return;
            dc.DrawRectangle(Brushes.Transparent, null, new Rect(0, 0, ActualWidth, ActualHeight));   // zona de clic
            dc.DrawRoundedRectangle(new SolidColorBrush(Theme.WithAlpha(_dim, 0.35)), null, new Rect(pad, y - 2, w, 4), 2, 2);
            var col = _muted ? _dim : _accent;
            double fill = w * _value;
            if (fill > 0) dc.DrawRoundedRectangle(new SolidColorBrush(col), null, new Rect(pad, y - 2, fill, 4), 2, 2);
            // marcas cada 25 %
            for (int i = 1; i < 4; i++)
                dc.DrawRectangle(new SolidColorBrush(Theme.WithAlpha(_dim, 0.5)), null, new Rect(pad + w * i / 4 - 0.5, y + 4, 1, 3));
            dc.DrawEllipse(new SolidColorBrush(Theme.WithAlpha(col, 0.25)), null, new Point(pad + fill, y), 9, 9);
            dc.DrawEllipse(new SolidColorBrush(Colors.White), new Pen(new SolidColorBrush(col), 2), new Point(pad + fill, y), 5.5, 5.5);
        }
    }
}
