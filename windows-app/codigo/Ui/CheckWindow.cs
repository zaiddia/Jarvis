using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Jarvis.Ui
{
    // Resultado de una comprobación de la prueba completa.
    public enum CheckState { Ok, Warn, Fail, Info }

    public sealed class CheckItem
    {
        public string Group = "";
        public CheckState State;
        public string Text = "";
        public string FixLabel = "";
        public Action Fix;          // qué hace el botón «Arreglar» (abrir los ajustes de Windows, instalar voces…)

        public static CheckItem Of(string group, bool ok, string okText, string badText, string fixLabel = "", Action fix = null, bool onlyWarn = false) => new CheckItem
        {
            Group = group,
            State = ok ? CheckState.Ok : onlyWarn ? CheckState.Warn : CheckState.Fail,
            Text = ok ? okText : badText,
            FixLabel = ok ? "" : fixLabel,
            Fix = ok ? null : fix,
        };
    }

    // «Prueba completa»: micrófono, reconocimiento, voz, IA, internet e integraciones, en verde, ámbar o rojo,
    // con un botón para arreglar cada problema y otro para copiar el informe.
    public sealed class CheckWindow : Window
    {
        readonly StackPanel _list = new StackPanel();
        readonly TextBlock _status = new TextBlock { Margin = new Thickness(0, 0, 0, 6), TextWrapping = TextWrapping.Wrap, FontSize = 14 };
        readonly List<CheckItem> _items = new List<CheckItem>();
        readonly Button _again;
        string _group = "";
        public event Action RunAgain;
        public string Version = "";

        static readonly SolidColorBrush Green = new SolidColorBrush(Color.FromRgb(0x1E, 0x9E, 0x5A));
        static readonly SolidColorBrush Amber = new SolidColorBrush(Color.FromRgb(0xD9, 0x8E, 0x04));
        static readonly SolidColorBrush Red = new SolidColorBrush(Color.FromRgb(0xD6, 0x2D, 0x3C));
        static readonly SolidColorBrush Blue = new SolidColorBrush(Color.FromRgb(0x0B, 0x5C, 0x8E));

        public CheckWindow(string name)
        {
            Title = "Prueba completa de " + name;
            Width = 620;
            Height = Math.Min(680, SystemParameters.WorkArea.Height - 40);
            MinWidth = 460;
            MinHeight = 360;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            FontFamily = new FontFamily("Segoe UI Variable Text, Segoe UI");
            FontSize = 13;
            try { Icon = System.Windows.Media.Imaging.BitmapFrame.Create(new Uri("pack://application:,,,/jarvis.ico")); } catch { }

            var dock = new DockPanel { Margin = new Thickness(16) };
            var head = new StackPanel();
            head.Children.Add(new TextBlock { Text = "Prueba completa", FontSize = 20, FontWeight = FontWeights.SemiBold, Foreground = Blue, FontFamily = new FontFamily("Bahnschrift, Segoe UI") });
            head.Children.Add(_status);
            DockPanel.SetDock(head, Dock.Top);
            dock.Children.Add(head);

            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 10, 0, 0) };
            _again = new Button { Content = "Repetir", Width = 110, Height = 30, Margin = new Thickness(0, 0, 8, 0), IsEnabled = false };
            _again.Click += (o, e) => RunAgain?.Invoke();
            var copy = new Button { Content = "Copiar informe", Width = 130, Height = 30, Margin = new Thickness(0, 0, 8, 0) };
            copy.Click += (o, e) =>
            {
                try
                {
                    Clipboard.SetText(Report());
                    _status.Text = "Informe copiado. Péguelo donde lo necesite (por ejemplo, en el chat con Claude).";
                }
                catch { }
            };
            var close = new Button { Content = "Cerrar", Width = 110, Height = 30, IsCancel = true };
            close.Click += (o, e) => Close();
            buttons.Children.Add(_again);
            buttons.Children.Add(copy);
            buttons.Children.Add(close);
            DockPanel.SetDock(buttons, Dock.Bottom);
            dock.Children.Add(buttons);

            dock.Children.Add(new ScrollViewer { Content = _list, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
            Content = dock;
        }

        public void Begin()
        {
            _items.Clear();
            _list.Children.Clear();
            _group = "";
            _again.IsEnabled = false;
            _status.Text = "Comprobando… (tarda unos segundos)";
            _status.Foreground = Brushes.Gray;
        }

        public void Add(CheckItem it)
        {
            _items.Add(it);
            if (it.Group != _group)
            {
                _group = it.Group;
                _list.Children.Add(new TextBlock { Text = it.Group, FontWeight = FontWeights.SemiBold, FontSize = 14, Foreground = Blue, Margin = new Thickness(0, _list.Children.Count == 0 ? 4 : 14, 0, 4) });
            }
            var row = new DockPanel { Margin = new Thickness(0, 2, 0, 2), LastChildFill = true };
            var mark = new TextBlock
            {
                Text = it.State switch { CheckState.Ok => "✓", CheckState.Warn => "!", CheckState.Fail => "✗", _ => "•" },
                Foreground = it.State switch { CheckState.Ok => Green, CheckState.Warn => Amber, CheckState.Fail => Red, _ => Brushes.Gray },
                FontWeight = FontWeights.Bold,
                Width = 22,
                FontSize = 15,
            };
            DockPanel.SetDock(mark, Dock.Left);
            row.Children.Add(mark);
            if (it.Fix != null)
            {
                var fix = new Button { Content = it.FixLabel == "" ? "Arreglar" : it.FixLabel, Padding = new Thickness(10, 2, 10, 2), Margin = new Thickness(8, 0, 0, 0), VerticalAlignment = VerticalAlignment.Top };
                fix.Click += (o, e) => { try { it.Fix(); } catch (Exception ex) { MessageBox.Show(ex.Message, Title); } };
                DockPanel.SetDock(fix, Dock.Right);
                row.Children.Add(fix);
            }
            row.Children.Add(new TextBlock { Text = it.Text, TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center });
            _list.Children.Add(row);
        }

        public void Done()
        {
            _again.IsEnabled = true;
            int bad = _items.Count(i => i.State == CheckState.Fail), warn = _items.Count(i => i.State == CheckState.Warn);
            _status.Text = bad == 0 && warn == 0 ? "Todo en orden." :
                           (bad > 0 ? bad + (bad == 1 ? " problema" : " problemas") : "") + (bad > 0 && warn > 0 ? " y " : "") +
                           (warn > 0 ? warn + (warn == 1 ? " aviso" : " avisos") : "") + ". Pulse «Arreglar» donde aparezca.";
            _status.Foreground = bad > 0 ? Red : warn > 0 ? Amber : Green;
        }

        public IReadOnlyList<CheckItem> Items => _items;

        string Report()
        {
            var sb = new StringBuilder();
            sb.AppendLine("Prueba completa de JARVIS " + Version + " — " + DateTime.Now.ToString("yyyy-MM-dd HH:mm"));
            sb.AppendLine("Windows " + Environment.OSVersion.Version);
            string g = "";
            foreach (var i in _items)
            {
                if (i.Group != g) { g = i.Group; sb.AppendLine().AppendLine("[" + g + "]"); }
                sb.AppendLine((i.State switch { CheckState.Ok => "OK   ", CheckState.Warn => "AVISO", CheckState.Fail => "FALLO", _ => "INFO " }) + " " + i.Text);
            }
            return sb.ToString();
        }
    }
}
