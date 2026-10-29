using System;
using System.Net;
using System.Net.Http;

namespace Jarvis.Core
{
    // Clientes HTTP de larga vida bien configurados: reciclan las conexiones cada 15 minutos
    // (así notan los cambios de DNS o de red) y descomprimen gzip, deflate y brotli.
    public static class Net
    {
        public static HttpClient Create(TimeSpan timeout)
        {
            var handler = new SocketsHttpHandler
            {
                PooledConnectionLifetime = TimeSpan.FromMinutes(15),
                AutomaticDecompression = DecompressionMethods.All,
                ConnectTimeout = TimeSpan.FromSeconds(15),
            };
            return new HttpClient(handler) { Timeout = timeout };
        }
    }
}
