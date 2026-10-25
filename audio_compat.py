"""Adaptador mínimo con la misma API que PyAudio, construido sobre sounddevice.

PyAudio no publica instaladores para las versiones nuevas de Python (3.14+) y
compilarlo exige Visual C++. sounddevice trae PortAudio incluido y se instala en
cualquier versión, así que Jarvis lo usa automáticamente cuando falta PyAudio.
Solo implementa lo que Jarvis necesita: listar micrófonos y leer audio int16.
"""
import sounddevice as sd

paInt16 = 8          # mismo valor que pyaudio.paInt16


class _Stream:
    def __init__(self, rate, channels, frames_per_buffer, device):
        self._s = sd.RawInputStream(samplerate=rate, channels=channels, dtype="int16",
                                    blocksize=frames_per_buffer, device=device)
        self._s.start()

    def read(self, frames, exception_on_overflow=False):
        data, overflowed = self._s.read(frames)
        if overflowed and exception_on_overflow:
            raise IOError("Input overflowed")
        return bytes(data)

    def stop_stream(self):
        try:
            self._s.stop()
        except Exception:
            pass

    def close(self):
        try:
            self._s.close()
        except Exception:
            pass


class PyAudio:
    def get_device_count(self):
        return len(sd.query_devices())

    def get_device_info_by_index(self, i):
        d = sd.query_devices(i)
        return {"index": i, "name": d["name"], "hostApi": d["hostapi"],
                "maxInputChannels": d["max_input_channels"],
                "defaultSampleRate": d["default_samplerate"]}

    def get_host_api_info_by_index(self, i):
        return {"index": i, "name": sd.query_hostapis(i)["name"]}

    def open(self, format=paInt16, channels=1, rate=16000, input=True,
             frames_per_buffer=4000, input_device_index=None, **_):
        return _Stream(rate, channels, frames_per_buffer, input_device_index)

    def terminate(self):
        pass
