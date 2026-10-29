using System;
using System.Windows;
using System.Windows.Media;

namespace Jarvis.Ui
{
    // El «reactor»: anillos que giran, arcos de datos y 36 barras que siguen la voz.
    public sealed class Reactor : FrameworkElement
    {
        readonly double[] _bars = new double[36];
        readonly double[] _target = new double[36];
        readonly Random _rnd = new Random();
        double _spin, _pulse;
        DateTime _last = DateTime.Now;
        Color _color = Colors.DeepSkyBlue, _goal = Colors.DeepSkyBlue;
        Theme _theme = Theme.Get("azul");
        HudState _state = HudState.Idle;
        double _level;           // 0…1, entrada externa (micrófono o voz)
        bool _running;

        public void SetTheme(Theme t)
        {
            _theme = t;
            _goal = t.For(_state);
        }

        public void SetState(HudState s)
        {
            _state = s;
            _goal = _theme.For(s);
        }

        public void SetLevel(double v) => _level = Math.Clamp(v, 0, 1);

        public void Start()
        {
            if (_running) return;
            _running = true;
            _last = DateTime.Now;
            CompositionTarget.Rendering += Tick;
        }

        public void Stop()
        {
            if (!_running) return;
            _running = false;
            CompositionTarget.Rendering -= Tick;
        }

        void Tick(object sender, EventArgs e)
        {
            var now = DateTime.Now;
            double dt = Math.Min(0.1, (now - _last).TotalSeconds);
            _last = now;
            double speed = _state == HudState.Thinking ? 2.6 : _state == HudState.Listening ? 1.2 : _state == HudState.Speaking ? 1.5 : 0.35;
            _spin = (_spin + dt * speed * 60) % 360;
            _pulse += dt * (_state == HudState.Thinking ? 6 : 2.2);
            _color = Theme.Mix(_color, _goal, Math.Min(1, dt * 6));

            double lvl = _level;
            if (_state == HudState.Thinking) lvl = 0.25 + 0.15 * Math.Sin(_pulse);
            if (_state == HudState.Idle || _state == HudState.Muted) lvl *= 0.3;
            for (int i = 0; i < _bars.Length; i++)
            {
                if (_rnd.NextDouble() < 0.35)
                {
                    double shape = 0.55 + 0.45 * Math.Sin(i * 0.9 + _pulse * 1.7);
                    _target[i] = Math.Clamp(lvl * (0.5 + _rnd.NextDouble() * 0.8) * shape + 0.04, 0, 1);
                }
                _bars[i] += (_target[i] - _bars[i]) * Math.Min(1, dt * 14);
            }
            InvalidateVisual();
        }

        protected override void OnRender(DrawingContext dc)
        {
            double w = ActualWidth, h = ActualHeight;
            if (w <= 0 || h <= 0) return;
            var c = new Point(w / 2, h / 2);
            double r = Math.Min(w, h) / 2 - 2;
            var col = _color;

            Pen P(double a, double t) => new Pen(new SolidColorBrush(Theme.WithAlpha(col, a)), t);

            // resplandor del núcleo
            var glow = new RadialGradientBrush(Theme.WithAlpha(col, 0.55 + 0.15 * Math.Sin(_pulse)), Theme.WithAlpha(col, 0));
            dc.DrawEllipse(glow, null, c, r * 0.62, r * 0.62);

            // barras de voz
            for (int i = 0; i < _bars.Length; i++)
            {
                double ang = (i * 10 + _spin * 0.25) * Math.PI / 180;
                double r0 = r * 0.56, r1 = r0 + r * 0.30 * _bars[i] + 1.5;
                var a = new Point(c.X + Math.Cos(ang) * r0, c.Y + Math.Sin(ang) * r0);
                var b = new Point(c.X + Math.Cos(ang) * r1, c.Y + Math.Sin(ang) * r1);
                dc.DrawLine(P(0.35 + 0.65 * _bars[i], 2.2), a, b);
            }

            // anillos
            dc.DrawEllipse(null, P(0.85, 1.6), c, r * 0.97, r * 0.97);
            dc.DrawEllipse(null, P(0.25, 1), c, r * 0.90, r * 0.90);
            dc.DrawEllipse(null, P(0.4, 1), c, r * 0.52, r * 0.52);

            // arcos que giran en sentidos opuestos
            Arc(dc, c, r * 0.93, _spin, 70, P(0.95, 3));
            Arc(dc, c, r * 0.93, _spin + 180, 40, P(0.7, 3));
            Arc(dc, c, r * 0.84, -_spin * 1.4, 110, P(0.6, 1.4));
            Arc(dc, c, r * 0.84, -_spin * 1.4 + 200, 50, P(0.45, 1.4));
            Arc(dc, c, r * 0.47, _spin * 2, 90, P(0.8, 2));

            // marcas del anillo exterior
            for (int i = 0; i < 60; i++)
            {
                double ang = i * 6 * Math.PI / 180;
                double l = i % 5 == 0 ? 0.07 : 0.035;
                dc.DrawLine(P(i % 5 == 0 ? 0.7 : 0.3, 1),
                    new Point(c.X + Math.Cos(ang) * r, c.Y + Math.Sin(ang) * r),
                    new Point(c.X + Math.Cos(ang) * r * (1 - l), c.Y + Math.Sin(ang) * r * (1 - l)));
            }

            // núcleo
            var core = new RadialGradientBrush(Color.FromArgb(255, 255, 255, 255), Theme.WithAlpha(col, 0.9)) { GradientOrigin = new Point(0.45, 0.4) };
            double cr = r * (0.2 + 0.015 * Math.Sin(_pulse * 1.3)) * (1 + _level * 0.15);
            dc.DrawEllipse(core, P(1, 1.5), c, cr, cr);
            // triángulo interior estilo Mark
            var tri = new StreamGeometry();
            using (var g = tri.Open())
            {
                for (int k = 0; k < 3; k++)
                {
                    double ang = (-90 + k * 120 + _spin * 0.5) * Math.PI / 180;
                    var p = new Point(c.X + Math.Cos(ang) * cr * 0.7, c.Y + Math.Sin(ang) * cr * 0.7);
                    if (k == 0) g.BeginFigure(p, false, true);
                    else g.LineTo(p, true, false);
                }
            }
            dc.DrawGeometry(null, new Pen(new SolidColorBrush(Theme.WithAlpha(Theme.Mix(col, Colors.White, 0.3), 0.8)), 1.2), tri);
        }

        static void Arc(DrawingContext dc, Point c, double r, double startDeg, double sweepDeg, Pen pen)
        {
            double a0 = startDeg * Math.PI / 180, a1 = (startDeg + sweepDeg) * Math.PI / 180;
            var p0 = new Point(c.X + Math.Cos(a0) * r, c.Y + Math.Sin(a0) * r);
            var p1 = new Point(c.X + Math.Cos(a1) * r, c.Y + Math.Sin(a1) * r);
            var g = new StreamGeometry();
            using (var ctx = g.Open())
            {
                ctx.BeginFigure(p0, false, false);
                ctx.ArcTo(p1, new Size(r, r), 0, sweepDeg > 180, SweepDirection.Clockwise, true, false);
            }
            dc.DrawGeometry(null, pen, g);
        }
    }
}
