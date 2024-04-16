# anim_pcb
Command line utility creating raytraced/rendered animation videos from a collection of parameters and an arbitrary .kicad_pcb file using the new-ish "pcb render" image export feature in kicad-cli-nightly together with ffmpeg as the final step. Multiple kicad-cli-nightly instances are run in parallel, the raytracing in kicad-cli-nightly is very CPU bound and one instance per core reduces the time of the entire adventure almost to 1/#cores.


anim_pcb arguments help `./anim_pcb -h`

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

