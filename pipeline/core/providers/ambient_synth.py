"""Procedural ambient synthesizer (ffmpeg lavfi): free, deterministic, no licensing.

Generates an ambient bed of exactly the requested duration from noise/oscillator
primitives — the "фоновой музыки" for sleep-history episodes without any external
service. Moods: night / rain / wind / drone / fire / space.

v2 (2026-10-05): layered graphs — each mood stacks 3-5 sources (rumble bed,
mid band, sparkle/crackle) with independent filtering, slow tremolo swells at
different rates and a soft room echo, then amix + make-up gain + limiter.
Sounds noticeably fuller than the single-oscillator v1.
"""

from pathlib import Path

from core.providers.router import Provider, ProviderError
from core.media import ff

MOODS = ["night", "rain", "wind", "drone", "fire", "space"]


def _src(i: int, label: str, chain: str) -> str:
    return f"[{i}:a]{chain}[{label}]"


def _mix(labels: list[str], gain: float, mood_tremolo: str, echo: str, dur: float) -> str:
    """amix(labels) -> gain -> slow swells -> echo -> fades -> [aout]."""
    D = f"{max(dur, 5):.2f}"
    fade = f"afade=t=in:d=3,afade=t=out:st={max(dur - 4, 0):.2f}:d=4"
    n = len(labels)
    ins = "".join(f"[{x}]" for x in labels)
    return (f"{ins}amix=inputs={n}:normalize=0,"
            f"volume={gain},{mood_tremolo},{echo},{fade},alimiter=limit=0.9[aout]")


def _synth_filtergraph(mood: str, dur: float) -> tuple[list[str], str]:
    """Return (input_args, filter_complex) for the mood."""
    D = f"{max(dur, 5):.2f}"
    chains: list[tuple[list[str], str]] = []  # (input_args_for_this_source, chain)

    if mood == "rain":
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.30:duration={D}:seed=7"],
                       "lowpass=f=240,volume=0.55"))                      # distant rumble bed
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.55:duration={D}:seed=8"],
                       "highpass=f=700,lowpass=f=3400,volume=0.55"))      # rain body
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=white:amplitude=0.14:duration={D}:seed=9"],
                       "highpass=f=4600,volume=0.40"))                    # patter sparkle
        echo = "aecho=0.6:0.4:70|140:0.18|0.10"
        trem = "volume='0.85+0.15*sin(2*PI*t/17)':eval=frame"
        gain = 2.6
    elif mood == "wind":
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.75:duration={D}:seed=11"],
                       "lowpass=f=480,volume=0.75"))                      # main gust bed
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.40:duration={D}:seed=12"],
                       "highpass=f=520,lowpass=f=1500,volume=0.45"))      # whistle band
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.22:duration={D}:seed=13"],
                       "lowpass=f=300,volume=0.40"))                      # deep floor
        echo = "aecho=0.7:0.5:90|180:0.20|0.12"
        # two incommensurate sines -> irregular gusting
        trem = "volume='0.62+0.38*sin(2*PI*t/23)*sin(2*PI*t/7.3)':eval=frame"
        gain = 1.8
    elif mood == "drone":
        for f_, a in [(48, 0.50), (48.35, 0.50), (72, 0.30), (96, 0.22), (144.8, 0.12)]:
            chains.append((["-f", "lavfi", "-i", f"sine=frequency={f_}:duration={D}"],
                           f"volume={a}"))
        echo = "aecho=0.75:0.6:120|240:0.32|0.20"
        trem = "volume='0.78+0.22*sin(2*PI*t/31)':eval=frame"
        gain = 1.2
    elif mood == "fire":
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.55:duration={D}:seed=3"],
                       "lowpass=f=700,volume=0.80"))                      # roar bed
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=white:amplitude=0.09:duration={D}:seed=9"],
                       "agate=threshold=0.78:ratio=9:attack=1:release=25,highpass=f=2200,volume=1.7"))
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=white:amplitude=0.07:duration={D}:seed=31"],
                       "agate=threshold=0.84:ratio=12:attack=1:release=15,highpass=f=3200,volume=1.9"))
        echo = "aecho=0.5:0.35:60:0.12"
        trem = "volume='0.85+0.15*sin(2*PI*t/11)':eval=frame"
        gain = 1.85
    elif mood == "space":
        for f_, a in [(110, 0.22), (110.6, 0.22), (220, 0.18), (330.2, 0.10)]:
            chains.append((["-f", "lavfi", "-i", f"sine=frequency={f_}:duration={D}"],
                           f"volume={a}"))
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.04:duration={D}:seed=21"],
                       "highpass=f=6000,volume=0.45"))                    # shimmer
        echo = "aecho=0.7:0.55:140|280:0.30|0.20"
        trem = "volume='0.72+0.28*sin(2*PI*t/19)':eval=frame"
        gain = 2.2
    else:  # night — тёплый бьющийся дрон + тихий розовый шум
        for f_, a in [(82.4, 0.30), (82.9, 0.30), (123.5, 0.18), (164.8, 0.12)]:
            chains.append((["-f", "lavfi", "-i", f"sine=frequency={f_}:duration={D}"],
                           f"volume={a}"))
        chains.append((["-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.10:duration={D}:seed=5"],
                       "lowpass=f=700,volume=0.35"))
        echo = "aecho=0.7:0.55:110|220:0.28|0.16"
        trem = "volume='0.78+0.22*sin(2*PI*t/27)':eval=frame"
        gain = 1.85

    ins: list[str] = []
    labels = []
    for i, (src_args, chain) in enumerate(chains):
        ins.extend(src_args)
        labels.append(f"s{i}")
    parts = [_src(i, labels[i], chain) for i, (src_args, chain) in enumerate(chains)]
    fc = ";".join(parts + [_mix(labels, gain, trem, echo, dur)])
    return ins, fc


class AmbientSynthProvider(Provider):
    adapter = "ambient_synth"

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("ambient_synth: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        mood = (payload.get("mood") or self.cfg.get("mood") or "night").lower()
        if mood not in MOODS:
            mood = "night"
        dur = float(payload.get("duration_sec", 60))
        ins, fc = _synth_filtergraph(mood, dur)
        ff(["-y", *ins, "-filter_complex", fc, "-map", "[aout]",
            "-c:a", "aac", "-b:a", "128k", str(out)])
        return {"audio_path": str(out), "mood": mood}
