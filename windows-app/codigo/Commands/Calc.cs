using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Cuentas dichas en español: «cuánto es 25 por 4 más 3», «raíz cuadrada de 144», «el 15 por ciento de 80».
    public static class Calc
    {
        static readonly string[] Starters = { "cuanto es", "cuanto son", "calcula", "cuanto da", "resuelve", "cuanto seria", "cuanto hace" };

        public static bool LooksLikeMath(string folded)
        {
            string s = " " + Text.Squash(folded) + " ";
            if (Starters.Any(st => s.StartsWith(" " + st + " "))) return true;
            return Regex.IsMatch(folded, @"^\s*[\d(][\d\s.,()+\-*/x^%]*$") && Regex.IsMatch(folded, @"\d\s*[+\-*/x^%]\s*\d");
        }

        // Devuelve el texto de la respuesta o null si no es una cuenta.
        public static string Answer(string text, string sir)
        {
            string f = Text.FoldText(text);
            if (!LooksLikeMath(f)) return null;
            var toks = Tokenize(f);
            if (toks == null || toks.Count == 0) return null;
            if (!toks.Any(t => t is double) || !toks.Any(t => t is string op && "+-*/^%√".Contains(op))) return null;
            try
            {
                int i = 0;
                double v = Expr(toks, ref i);
                if (i != toks.Count) return null;
                if (double.IsNaN(v)) return "Esa cuenta no tiene resultado" + sir + ".";
                if (double.IsInfinity(v)) return "No se puede dividir entre cero" + sir + ".";
                return Pick() + Format(v) + ".";
            }
            catch
            {
                return null;
            }
        }

        static readonly Random Rnd = new Random();
        static string Pick() => new[] { "Son ", "Da ", "El resultado es " }[Rnd.Next(3)];

        public static string Format(double v)
        {
            if (Math.Abs(v) >= 1e12) return v.ToString("0.###E+0", CultureInfo.InvariantCulture).Replace('.', ',');
            double r = Math.Round(v, Math.Abs(v) < 1 ? 6 : 4);
            return Text.Num(r, Math.Abs(v) < 1 ? 6 : 4);
        }

        static readonly Dictionary<string, string> Ops = new Dictionary<string, string>
        {
            ["mas"] = "+", ["menos"] = "-", ["por"] = "*", ["x"] = "*", ["multiplicado"] = "*", ["veces"] = "*",
            ["entre"] = "/", ["dividido"] = "/", ["sobre"] = "/", ["partido"] = "/",
        };

        static List<object> Tokenize(string f)
        {
            var o = new List<object>();
            var m = Regex.Matches(f, @"\d+(?:[.,]\d+)*|[a-z]+|[+\-*/^()%×÷]");
            var words = m.Select(x => x.Value).ToList();
            int i = 0;
            // Saltar «cuánto es», «calcula»…
            while (i < words.Count && Text.IsOneOf(words[i], "cuanto", "es", "son", "calcula", "da", "resuelve", "seria", "hace", "me", "dime", "el", "la", "cuantos", "y")) i++;
            for (; i < words.Count; i++)
            {
                string w = words[i];
                if (char.IsDigit(w[0]))
                {
                    if (!Text.TryParseDecimal(w, out double d)) return null;
                    o.Add(d);
                    continue;
                }
                if (w == "×") { o.Add("*"); continue; }
                if (w == "÷") { o.Add("/"); continue; }
                if ("+-*/^()%".Contains(w)) { o.Add(w); continue; }
                if (w == "por" && i + 1 < words.Count && (words[i + 1] == "ciento" || words[i + 1] == "cien"))
                {
                    o.Add("%");
                    i++;
                    if (i + 1 < words.Count && words[i + 1] == "de") i++;
                    continue;
                }
                if (Ops.TryGetValue(w, out string op))
                {
                    o.Add(op);
                    if (i + 1 < words.Count && (words[i + 1] == "por" && op == "*" || words[i + 1] == "entre" || words[i + 1] == "de")) i++;
                    continue;
                }
                if (w == "elevado")
                {
                    o.Add("^");
                    if (i + 1 < words.Count && words[i + 1] == "a") i++;
                    continue;
                }
                if (w == "al" && i + 1 < words.Count && (words[i + 1] == "cuadrado" || words[i + 1] == "cubo"))
                {
                    o.Add("^");
                    o.Add(words[i + 1] == "cuadrado" ? 2.0 : 3.0);
                    i++;
                    continue;
                }
                if (w == "raiz")
                {
                    o.Add("√");
                    while (i + 1 < words.Count && Text.IsOneOf(words[i + 1], "cuadrada", "de")) i++;
                    continue;
                }
                if (w == "mitad" || w == "doble" || w == "triple")
                {
                    o.Add(w == "mitad" ? 0.5 : w == "doble" ? 2.0 : 3.0);
                    o.Add("*");
                    if (i + 1 < words.Count && words[i + 1] == "de") i++;
                    continue;
                }
                // números en palabras: «treinta y cinco», «mil doscientos», «un millón»
                int n = WordNumber(words, ref i);
                if (n >= 0) { o.Add((double)n); continue; }
                if (Text.IsOneOf(w, "de", "el", "la", "los", "las", "cuanto", "es", "igual", "a", "da")) continue;
                return null;
            }
            // «el 15 % de 80» → 15 % 80
            return o;
        }

        static int WordNumber(List<string> w, ref int i)
        {
            long total = 0, cur = 0;
            int start = i;
            bool any = false;
            while (i < w.Count)
            {
                string s = w[i];
                if (s == "mil") { cur = Math.Max(cur, 1) * 1000; total += cur; cur = 0; any = true; i++; continue; }
                if (s == "millon" || s == "millones") { cur = Math.Max(cur, 1) * 1000000; total += cur; cur = 0; any = true; i++; continue; }
                if (s == "ciento") { cur += 100; any = true; i++; continue; }
                if (s == "y" && any && i + 1 < w.Count && Text.ParseNumber(w[i + 1], true) is int u && u >= 1 && u <= 9 && cur % 10 == 0 && cur % 100 >= 30) { i++; continue; }
                int n = Text.ParseNumber(s, true);
                if (n < 0 || char.IsDigit(s[0]) || s == "maximo" || s == "tope" || s == "minimo") break;
                cur += n;
                any = true;
                i++;
            }
            if (!any) { i = start; return -1; }
            i--;
            return (int)Math.Min(int.MaxValue, total + cur);
        }

        // Gramática: expr = term (('+'|'-') term)* ; term = pow (('*'|'/'|'%') pow)* ; pow = unary ('^' pow)? ; unary = '-' unary | '√' unary | atom
        static double Expr(List<object> t, ref int i)
        {
            double v = Term(t, ref i);
            while (i < t.Count && t[i] is string op && (op == "+" || op == "-"))
            {
                i++;
                // «200 más el 10 %»
                double r = Term(t, ref i);
                if (i < t.Count && t[i] is string p && p == "%" && (i + 1 == t.Count || t[i + 1] is string)) { i++; r = v * r / 100; }
                v = op == "+" ? v + r : v - r;
            }
            return v;
        }

        static double Term(List<object> t, ref int i)
        {
            double v = Pow(t, ref i);
            while (i < t.Count && t[i] is string op && (op == "*" || op == "/" || op == "%"))
            {
                if (op == "%" && (i + 1 >= t.Count || t[i + 1] is string s && s != "(" && s != "√" && s != "-")) break;
                i++;
                double r = Pow(t, ref i);
                v = op == "*" ? v * r : op == "/" ? (r == 0 ? double.PositiveInfinity : v / r) : v * r / 100;
            }
            return v;
        }

        static double Pow(List<object> t, ref int i)
        {
            double b = Unary(t, ref i);
            if (i < t.Count && t[i] is string op && op == "^")
            {
                i++;
                return Math.Pow(b, Pow(t, ref i));
            }
            return b;
        }

        static double Unary(List<object> t, ref int i)
        {
            if (i >= t.Count) throw new FormatException();
            if (t[i] is string s)
            {
                if (s == "-") { i++; return -Unary(t, ref i); }
                if (s == "√") { i++; return Math.Sqrt(Unary(t, ref i)); }
                if (s == "(")
                {
                    i++;
                    double v = Expr(t, ref i);
                    if (i < t.Count && t[i] is string c && c == ")") i++;
                    return v;
                }
                throw new FormatException();
            }
            return (double)t[i++];
        }
    }
}
