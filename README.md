# anim_pcb
Command line utility creating raytraced/rendered animation videos from a collection of parameters and an arbitrary .kicad_pcb file using the new-ish "pcb render" image export feature in kicad-cli-nightly together with ffmpeg as the final step. Multiple kicad-cli-nightly instances are run in parallel, the raytracing in kicad-cli-nightly is very CPU bound and one instance per core reduces the time of the entire adventure almost to 1/#cores.

The code is written in Python by me - not being a Python programmer - prioritizing function over form. Caveat emptor.

anim_pcb arguments help including the animation description syntax:`./anim_pcb -h`

<details>
<summary>./anim_pcb -h</summary><p>

```
[...]$ ./anim_pcb.py -h
usage: anim_pcb.py [-h] [-d] [-nc] [-C] [--cli </path/to/kicad-cli>] [--dry-run] [--ffmpeg </path/to/ffmpeg>] [--fps <integer>]
                   [--img_format jpg|png] [-j <integer>] [--out <file>] [--tmpdir <directory>] [--kc-background transparent|opaque]
                   [--kc-quality basic|high|user] [--kc-preset <preset>] [--kc-floor] [--no-kc-perspective] --in <file> --res <XxY> -s
                   <segm_expr>

Parallellized PCB animation video creation by calling multiple kicad-cli-nightly instances repeatedly to render the individual frames, then optionally joining the created image files to a video with ffmpeg.

options:
  -h, --help            show this help message and exit
  -d, --debug           debug mode
  -nc, --nocolor, --nocolour
                        disable color output in terminal messages
  -C, --overwrite       overwrite existing images
  --cli </path/to/kicad-cli>
                        kicad-cli executable (default: kicad-cli-nightly)
  --dry-run             go through all motions except modifying any files
  --ffmpeg </path/to/ffmpeg>
                        ffmpeg executable (default: ffmpeg)
  --fps <integer>       video framerate (default: 30)
  --img_format jpg|png  image format of frames (default: png)
  -j <integer>, --jobs <integer>
                        maximum number of concurrent jobs, [1..8] (default: 8)
  --out <file>          output video file, e.g. "video.mp4". If absent, the frames will be rendered but no video created
  --tmpdir <directory>  tmp file directory (default: .)

options used when calling kicad-cli[-nightly]:
  --kc-background transparent|opaque
                        (default: transparent)
  --kc-quality basic|high|user
                        (default: high)
  --kc-preset <preset>  (default: follow_pcb_editor)
  --kc-floor            (default: not used)
  --no-kc-perspective   do NOT use --perspective (default: False)

required arguments:
  --in <file>           .kicad_pcb file
  --res <XxY>           target video resolution, e.g. 640x480
  -s <segm_expr>, --segment <segm_expr>
                        add video segment. More than one --segment can be specified. See below for syntax.

Rotation and zoom seem usable, pan and pivot are more or less untested.

Multiple --segment args can be used. The resulting video will have them following each other in-order. The "from"-params of the 2nd segment should in that case be equal to the "toward"-params of the 1st, etc for continuous, seamless movement.

############### --segment "segm_expr" indepth ###############

Whitespace separating parts can be any length.

"1.3s   z(0.9) rot(1, 2, 3) pan(0,0,0) piv(0,0,0) ->            z(0.9) rot(4, 5, 6) pan(0,0,0) piv(0,0,0)"

Semiformal syntax description of segm_expr:

segm_expr       ::= dur_expr WS from_expr WS "->" WS toward_expr
from_expr       ::= toward_expr
toward_expr     ::= [zoom_expr] [rot_expr] [pan_expr] [piv_expr]
dur_expr        ::= floatnumber ("s" | "ms")
zoom_expr       ::= "z" "(" [WS] floatnumber [WS] ")"
rot_expr        ::= "rot" "(" [WS] rotax [WS] "," [WS] rotay [WS] "," [WS] rotaz [WS] ")"
pan_expr        ::= "pan" "(" [WS] panax [WS] "," [WS] panay [WS] "," [WS] panaz [WS] ")"
piv_expr        ::= "piv" "(" [WS] pivx [WS] "," [WS] pivy [WS] "," [WS] pivz [WS] ")"
rotax..z        ::= floatnumber
panax..z        ::= floatnumber
pivx..z         ::= floatnumber
WS                      ::= (SP | TAB | NEWLINE)*

Animation is made by interpolating the positional parameters between (from_expr) and (toward_expr) in the intermediate frames.

It's questionable if pivot animation is useful, but it can be, in the interest of flexibility.

(duration) is the target playing time of the animation segment. The animation segment will consist of (fps * duration in s) frames.

(zoom) is the camera zoomin. If absent, 1.0 is used.

(rotax, rotay, rotaz) define the PCBs rotation around the x,y,z-axii. If absent, (0,0,0) are used. kicad-cli-nightly seems to dislike angles outside the [-360..360] range, so don't use values outside this. TODO remainder division/normalize/direction arithmetic.

(panax, panay, panaz) define, if included, the viewpoint's panning.

(pivx, pivy, pivz) define, if included, the rotation pivot of the PCB in centimeters relative to its center.

############### Examples of segment expressions ###############
--segment "1500ms rot(0,0,0) -> rot(-180,30,45)"

equivalent generously fertilized with whitespace:
--segment "1.5s         rot(0, 0, 0)  ->    rot(-180, 30,   45)"

With two segments, first a 2s slow rotation, then a faster 1s one backwards to the video starting point:
--segment "2s   z(0.9)  rot(0,0,0)               ->     z(0.9) rot(-180,30,45)" --segment "1s   z(0.9)  rot(-180,30,45)  ->     z(0.9) rot(0,0,0)"

Zoom in from afar while rotating:
--segment "3s z(0.1) rot(90,90,0) -> z(0.9) rot(0,0,0)"
```

</p></details>

Also, see `kicad-cli-nightly pcb render --help`

## Demo case 1

```
[...]$ ./anim_pcb.py --overwrite --tmpdir dc1tmp --img_format jpg --fps 60 -j 7 --res 1280x1280 -s "3s z(0.4) rot(0,90,0)  piv(0,0,0) pan(10,20,30) -> z(0.9) pan(0,0,0) rot(0,0,0) piv(-5,7,0)" -s "5s z(0.9) piv(-5,7,0) rot(0,0,0) -> z(0.9) piv(0,0,0) rot(180,0,180)" -s "2s z(0.9) rot(180,0,180) pan(0,0,0) -> z(0.4) pan(10,20,30) rot(0,90,0)" --in ../../universellt_pcb/universellt_pcb.kicad_pcb --out video.mp4

[...]$ ls -l video.mp4
-rw-r--r-- 1 anders anders 20080286 16 apr 10.02 video.mp4
```

The resulting video looks nice, but is uncomfortably large, so I don't add it to the repository, lest GitHub's patience be tried. Instead, I use ImageMagick to create a montage/video contact sheet from the rendered images:

```
[...]$ magick montage ./dc1tmp/universellt_pcb.kicad_pcb.FRAME*.jpg -tile 16x  -geometry 48x48+0+0 assets/dc1.jpg
```

![Resulting image](/assets/dc1.jpg)

