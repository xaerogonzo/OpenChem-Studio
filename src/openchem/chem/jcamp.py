"""Reading JCAMP-DX spectra, so a prediction can be checked against one.

WHY THIS EXISTS. Every spectrum this application produces is currently
self-reported: the NMR predictors are scored against a held-out database
and the IR parser against NIST reference frequencies, but that scoring
happens in `benchmarks/`, offline, by a developer. A user looking at a
predicted spectrum has no way to put their own measured one beside it.
JCAMP-DX is the format instruments and spectral libraries actually emit,
so it is the one that closes that gap.

THE FORMAT IS OLDER AND STRANGER THAN IT LOOKS, and the compression is
where the bodies are. A JCAMP-DX file is `##KEY=value` headers followed by
an XYDATA table, and the Y values in that table may be written four
different ways, mixed freely on the same line:

    PAC  packed     plain numbers, separated by space, + or -
    SQZ  squeezed   leading digit replaced by a letter, sign encoded in
                    its case: @ABCDEFGHI is +0..+9, abcdefghi is -1..-9
    DIF  difference the value is a DELTA from the previous Y, not a value:
                    %JKLMNOPQR is +0..+9, jklmnopqr is -1..-9
    DUP  duplicate  STUVWXYZs means "repeat the previous Y 1..9 times"

The subtlety that makes DIF worth testing rather than eyeballing: after a
run of differences, the FIRST value on the next line is an absolute
Y-value check, not another difference. It repeats the last Y of the
previous line. A reader that treats it as data emits one extra point per
line and drifts the whole spectrum; a reader that treats it as a delta
corrupts every subsequent value. It is verified here and reported as a
corrupt file rather than silently accepted, because a spectrum that is
wrong by one point per line still looks entirely plausible.

X values are RECONSTRUCTED, not read. The `(X++(Y..Y))` form gives one X
per line and increments by `##DELTAX` for each Y after it -- so the X
column in the file is a checkpoint, not the data. Trusting it per line
would fail on exactly the files where it matters.

NOT VALIDATED AGAINST A REAL INSTRUMENT FILE. No JCAMP-DX file was
available on the reference machine, so every test here runs against
fixtures written by hand to exercise each encoding, plus a round trip.
That is enough to show the decoders are right about the SPEC; it is not
the same as showing they are right about what a particular vendor emits,
and vendor deviation is this format's main practical hazard. Treat a real
file that fails to load as a bug report worth having.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: SQZ: leading digit, sign in the case. "@" is +0, "a" is -1.
_SQZ = {c: i for i, c in enumerate("@ABCDEFGHI")}
_SQZ.update({c: -(i + 1) for i, c in enumerate("abcdefghi")})

#: DIF: the value is a difference from the previous Y. "%" is +0.
_DIF = {c: i for i, c in enumerate("%JKLMNOPQR")}
_DIF.update({c: -(i + 1) for i, c in enumerate("jklmnopqr")})

#: DUP: repeat the previous Y this many times. "S" is 1.
_DUP = {c: i + 1 for i, c in enumerate("STUVWXYZs")}


class JcampError(Exception):
    """Raised when a file is not readable as JCAMP-DX.

    Distinct from returning an empty spectrum: a file that does not parse
    is a fault the user needs to see, where a file with no data points is
    a legitimately empty measurement.
    """


@dataclass(frozen=True)
class JcampSpectrum:
    """One spectrum read from a JCAMP-DX file.

    `x` and `y` are plain lists in file order. No resampling, smoothing or
    unit conversion happens here -- this module's whole job is to return
    what the file says, and a comparison against a prediction is a
    different concern with different choices in it.
    """

    x: list[float]
    y: list[float]
    title: str = ""
    x_units: str = ""
    y_units: str = ""
    data_type: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def point_count(self) -> int:
        return len(self.x)

    def x_range(self) -> tuple[float, float]:
        return (min(self.x), max(self.x)) if self.x else (0.0, 0.0)


def parse(text: str) -> JcampSpectrum:
    """Read a JCAMP-DX document.

    Only the `(X++(Y..Y))` XYDATA form is supported, which is what IR and
    UV-Vis instruments emit. `(XY..XY)` peak tables are a different shape
    and are rejected by name rather than mis-read as this one.
    """
    headers: dict[str, str] = {}
    data_lines: list[str] = []
    in_data = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("$$"):
            continue
        if line.startswith("##"):
            key, _, value = line[2:].partition("=")
            key = key.strip().upper().replace(" ", "").replace("-", "").replace("_", "")
            value = value.strip()
            if key in ("XYDATA", "XYPOINTS", "PEAKTABLE"):
                if key != "XYDATA" or "X++" not in value.replace(" ", ""):
                    raise JcampError(
                        f"Unsupported data form {value!r}. This reader handles "
                        f"##XYDATA=(X++(Y..Y)), the form IR and UV-Vis "
                        f"instruments emit, not peak tables."
                    )
                in_data = True
                continue
            if key == "END":
                in_data = False
                continue
            headers[key] = value
            continue
        if in_data:
            data_lines.append(line)

    if not in_data and not data_lines:
        raise JcampError("No ##XYDATA block found.")

    x_factor = _number(headers.get("XFACTOR"), 1.0)
    y_factor = _number(headers.get("YFACTOR"), 1.0)
    delta_x = _number(headers.get("DELTAX"), 0.0)
    first_x = _number(headers.get("FIRSTX"), 0.0)
    last_x = _number(headers.get("LASTX"), 0.0)
    npoints = int(_number(headers.get("NPOINTS"), 0.0)) or 0

    if not delta_x and npoints > 1:
        # DELTAX is optional; the spacing is then implied by the endpoints.
        delta_x = (last_x - first_x) / (npoints - 1)

    y_values = _decode_lines(data_lines)
    if not y_values:
        raise JcampError("The ##XYDATA block contained no readable points.")

    # X is rebuilt from FIRSTX and DELTAX rather than taken per line -- the
    # per-line X is a checkpoint in this format, not the data.
    xs = [(first_x + i * delta_x) for i in range(len(y_values))]
    ys = [value * y_factor for value in y_values]
    if x_factor != 1.0:
        xs = [value * x_factor for value in xs]

    if npoints and npoints != len(ys):
        raise JcampError(
            f"##NPOINTS says {npoints} but {len(ys)} were decoded. The file "
            f"is inconsistent; refusing it rather than plotting a spectrum "
            f"that is the wrong length."
        )

    return JcampSpectrum(
        x=xs,
        y=ys,
        title=headers.get("TITLE", ""),
        x_units=headers.get("XUNITS", ""),
        y_units=headers.get("YUNITS", ""),
        data_type=headers.get("DATATYPE", ""),
        headers=headers,
    )


def _decode_lines(lines: list[str]) -> list[float]:
    """Decode every XYDATA line into one flat Y series."""
    ys: list[float] = []
    previous_line_ended_in_dif = False

    for line in lines:
        values, ended_in_dif = _decode_line(line)
        if not values:
            continue

        # THE Y-VALUE CHECK, and it applies ONLY after a DIF run. A line
        # following differences opens with an absolute repeat of the
        # previous line's last Y, so that value is a checkpoint and must be
        # dropped. A line following PAC or SQZ opens with ordinary data.
        #
        # Applying it unconditionally was the first version of this
        # function and it rejected every valid PAC file, because there the
        # opening value is simply the next point and has no reason to match
        # anything. Getting this backwards is silent in the other
        # direction: dropping a real point per line shortens the spectrum
        # and shifts every X after it.
        if ys and previous_line_ended_in_dif:
            if abs(values[0] - ys[-1]) > 1e-6:
                raise JcampError(
                    f"Y-value check failed: a line opens at {values[0]} where "
                    f"the previous line ended at {ys[-1]}. The file is corrupt "
                    f"or uses an encoding this reader does not handle."
                )
            ys.extend(values[1:])
        else:
            ys.extend(values)
        previous_line_ended_in_dif = ended_in_dif
    return ys


def _decode_line(line: str) -> tuple[list[float], bool]:
    """One XYDATA line -> its values, and whether it ended mid-DIF.

    The first token is the X checkpoint and is discarded; everything after
    it is Y data in any mix of the four encodings.
    """
    tokens = _tokenise(line)
    if len(tokens) < 2:
        return ([], False)

    values: list[float] = []
    ended_in_dif = False
    for token in tokens[1:]:
        kind, number = token
        if kind == "dup":
            if not values:
                raise JcampError("A duplicate count appeared before any value.")
            values.extend([values[-1]] * (int(number) - 1))
            continue
        if kind == "dif":
            if not values:
                raise JcampError("A difference appeared before any value.")
            values.append(values[-1] + number)
            ended_in_dif = True
            continue
        values.append(number)
        ended_in_dif = False
    return (values, ended_in_dif)


def _tokenise(line: str) -> list[tuple[str, float]]:
    """Split one line into (kind, value) pairs across all four encodings."""
    tokens: list[tuple[str, float]] = []
    index = 0
    length = len(line)

    while index < length:
        char = line[index]
        if char in " ,\t":
            index += 1
            continue

        if char in _DUP:
            digits, index = _trailing_digits(line, index + 1)
            tokens.append(("dup", float(str(_DUP[char]) + digits)))
            continue

        if char in _DIF:
            sign = -1 if char.islower() else 1
            digits, index = _trailing_digits(line, index + 1)
            tokens.append(("dif", sign * float(str(abs(_DIF[char])) + digits)))
            continue

        if char in _SQZ:
            sign = -1 if char.islower() else 1
            digits, index = _trailing_digits(line, index + 1)
            tokens.append(("val", sign * float(str(abs(_SQZ[char])) + digits)))
            continue

        # PAC: a plain signed number. A sign mid-line is a separator as
        # well as a sign, which is why this cannot be a simple split().
        start = index
        if char in "+-":
            index += 1
        while index < length and (line[index].isdigit() or line[index] in ".eE"):
            if line[index] in "eE" and index + 1 < length and line[index + 1] in "+-":
                index += 2
                continue
            index += 1
        chunk = line[start:index]
        if not chunk or chunk in "+-":
            index = start + 1
            continue
        try:
            tokens.append(("val", float(chunk)))
        except ValueError:
            pass
    return tokens


def _trailing_digits(line: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(line) and line[index].isdigit():
        index += 1
    return (line[start:index], index)


def _number(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        return float(raw.split()[0])
    except (ValueError, IndexError):
        return default
