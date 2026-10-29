using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using Jarvis.Core;

namespace Jarvis.Commands
{
    // Catálogo de lo que sabe hacer JARVIS, con órdenes de ejemplo que el motor entiende seguro.
    // La IA lo recibe para traducir lo que dice el usuario («está muy oscuro aquí») a una orden («sube el brillo»).
    // Las pruebas automáticas comprueban que cada ejemplo lo atiende de verdad alguna parte de JARVIS,
    // así el catálogo nunca promete algo que el motor no entiende.
    public static class Skills
    {
        public sealed class Skill
        {
            public string Area = "";
            public string What = "";
            public string[] Examples = new string[0];
            // Ejemplos que no se prueban solos (necesitan una ventana delante, una cuenta configurada
            // o harían algo molesto en el equipo de pruebas, como bloquearlo).
            public string[] Untested = new string[0];
        }

        static Skill S(string area, string what, string[] examples, params string[] untested) =>
            new Skill { Area = area, What = what, Examples = examples, Untested = untested };

        public static readonly Skill[] All =
        {
            S("Música y vídeo", "reproducir, pausar, cambiar de canción, saber qué suena, poner vídeos de YouTube, géneros y emisoras de radio",
              new[] { "pausa", "reanuda la música", "siguiente canción", "la anterior", "qué suena", "pon un video de Karol G", "pon salsa", "quiero escuchar a Shakira" },
              "pon la emisora La Mega"),
            S("Volumen", "subir, bajar, fijar o silenciar el volumen general o el de una aplicación",
              new[] { "sube el volumen", "baja el volumen", "volumen al 30", "silencia", "quita el silencio", "baja el volumen de spotify" }),
            S("Pantalla y ventanas", "brillo, modo oscuro, escritorio y ventanas",
              new[] { "sube el brillo", "baja el brillo al 30", "activa el modo oscuro", "muestra el escritorio", "cambia de ventana" },
              "minimiza", "maximiza", "pon esta ventana siempre encima"),
            S("Equipo", "bloquear, suspender, capturas de pantalla, papelera y estado del equipo",
              new string[0],
              "bloquea el equipo", "haz una captura", "vacía la papelera", "cuánta batería queda"),
            S("Programas y web", "abrir y cerrar programas, carpetas, ajustes de Windows y páginas; buscar en internet",
              new[] { "abre Spotify", "abre la calculadora", "abre la carpeta de descargas", "abre la configuración del wifi", "busca recetas de arepas" },
              "cierra el bloc de notas"),
            S("Hora y avisos", "hora, fecha, temporizadores, alarmas, recordatorios y cronómetro",
              new[] { "qué hora es", "qué día es hoy", "pon un temporizador de 10 minutos", "recuérdame en 20 minutos sacar la ropa",
                      "recuérdame mañana a las 9 llamar al banco", "pon una alarma a las 6 de la mañana", "qué alarmas tengo", "inicia el cronómetro" }),
            S("Información", "el tiempo, noticias, monedas, cuentas, conversiones y la hora en otras ciudades",
              new[] { "qué tiempo hace", "va a llover hoy", "cómo está el clima en Medellín", "noticias", "cuánto vale el dólar", "precio del bitcoin",
                      "cuánto es 25 por 4", "cuántos metros son 3 kilómetros", "qué hora es en Madrid" }),
            S("Notas, listas y memoria", "notas, listas de la compra y datos del usuario para recordar",
              new[] { "anota comprar pan", "añade leche a la lista de la compra", "qué hay en la lista de la compra", "recuerda que las llaves están en el cajón", "qué sabes de mí" }),
            S("Agenda", "eventos del calendario conectado",
              new string[0],
              "qué tengo hoy", "qué tengo mañana"),
            S("Casa y celular", "luces y aparatos de Home Assistant; mensajes al celular",
              new string[0],
              "enciende la luz de la sala", "apaga todas las luces", "mándame al celular que compre pan"),
            S("Rutinas", "rutinas que lanzan varias órdenes, a una hora o al encender",
              new[] { "qué rutinas tengo" }),
            S("Diversión", "chistes, datos curiosos, adivinanzas, moneda y dados",
              new[] { "cuéntame un chiste", "dime un dato curioso", "lanza una moneda", "dime una adivinanza" }),
            S("El propio asistente", "diagnóstico, ajustes y dejar de escuchar",
              new[] { "prueba completa", "diagnóstico de voz" },
              "abre tus ajustes", "deja de escuchar"),
        };

        public static IEnumerable<string> Tested => All.SelectMany(s => s.Examples);
        static IEnumerable<string> Everything => All.SelectMany(s => s.Examples.Concat(s.Untested));

        // Para las instrucciones de la IA: una línea por área.
        public static string Catalog()
        {
            var sb = new StringBuilder();
            foreach (var s in All)
                sb.Append("- ").Append(s.Area).Append(" (").Append(s.What).Append("): ")
                  .Append(string.Join(", ", s.Examples.Concat(s.Untested).Select(e => "«" + e + "»"))).Append('\n');
            return sb.ToString();
        }

        // Las órdenes del catálogo más parecidas a una que el motor no entendió (para que la IA lo intente con una válida).
        public static List<string> Closest(string order, int n = 4)
        {
            var words = Text.Squash(order).Split(' ', StringSplitOptions.RemoveEmptyEntries).Where(w => w.Length > 2).ToHashSet();
            if (words.Count == 0) return new List<string>();
            return Everything
                .Select(e => (e, score: Text.Squash(e).Split(' ').Count(w => w.Length > 2 && (words.Contains(w) || words.Any(x => x.Length > 4 && w.Length > 4 && x.Substring(0, 4) == w.Substring(0, 4))))))
                .Where(x => x.score > 0)
                .OrderByDescending(x => x.score)
                .Take(n)
                .Select(x => x.e)
                .ToList();
        }
    }
}
