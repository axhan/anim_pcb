#!/usr/bin/python3

import argparse, configparser, math, os.path, pathlib
import random, shlex, string, sys, subprocess
from dataclasses import dataclass, field

#***** Global variables ********************************************************
global glob 	# 8 marsSet to new instance of class Globals in main()
#***** Classes *****************************************************************

# ANSI-sequences for text styles and colours when print()ing in terminal.
# Never instantiated, its class attributes are referred directly.
class term:
	normal = reset = nor =	'\033[0m'
	bold =					'\033[01m'
	italics =				'\033[3m'
	underscore =			'\033[04m'
	reverse =				'\033[07m'
	overstrike =			'\033[09m'
	grey =					'\033[38;2;100;100;100m'
	white =					'\033[38;2;100;200;200m'
	green =					'\033[38;2;100;200;100m'
	orange =				'\033[38;2;230;100;100m'
	err =					normal + orange
	errdata =				normal + grey
	title =					normal + white
	values = value =		normal + green
	call = 					values + italics
	extra =					normal + grey
# /class term


# One instance for each "--segment" argument given on the commandline. Must
# contain all data necessary for 3D transition between frames within that segment.
@dataclass(eq=False)
class SegmentSpec:
	dur:		float	=	-1	# in s
	frames:		int		=	-1	# rounded up to nearest integer

	incl_zoom:	bool	=	 False
	incl_rot:	bool	=	 False
	incl_pan:	bool	=	 False
	incl_piv:	bool	=	 False

	fr_zoom:	float	=	1.0
	fr_rotax:	float	=	0
	fr_rotay:	float	=	0
	fr_rotaz:	float	=	0
	fr_panax:	float	=	0
	fr_panay:	float	=	0
	fr_panaz:	float	=	0
	fr_pivx:	float	=	0
	fr_pivy:	float	=	0
	fr_pivz:	float	=	0

	to_zoom:	float	=	1.0
	to_rotax:	float	=	0
	to_rotay:	float	=	0
	to_rotaz:	float	=	0
	to_panax:	float	=	0
	to_panay:	float	=	0
	to_panaz:	float	=	0
	to_pivx:	float	=	0
	to_pivy:	float	=	0
	to_pivz:	float	=	0

	d_zoom:		float	=	0
	d_rotax:	float	=	0
	d_rotay:	float	=	0
	d_rotaz:	float	=	0
	d_panax:	float	=	0
	d_panay:	float	=	0
	d_panaz:	float	=	0
	d_pivx:		float	=	0
	d_pivy:		float	=	0
	d_pivz:		float	=	0
# /class SegmentSpec


# Global variables kept in a class both to isolate their namespace and for aesthetics.
@dataclass(eq=False)
class Globals:
	# Settings from command line arguments
	pcb_file:		str			=	None
	out_file:		str			=	None
	ffmpeg_exe:		str			=	None
	img_format:		str			=	None
	kc_background:	str			=	None
	kc_floor:		bool		=	None
	kc_perspective:	bool		=	None
	kc_preset:		str			=	None
	kc_quality:		str			=	None
	kicad_cli_exe:	str			=	None
	nocolor:		bool		=	None
	overwrite:		bool		=	None
	debug_mode:		bool		=	None
	dry_run:		bool		=	None
	vid_fps:		int			=	None
	segment_args:	list[str]	=	field(default_factory=list)
	max_threads:	int			=	None
	img_suffix:		str			=	None
	tmp_dir:		str			=	None
	vid_res:		str			=	None

	# Settings calculated from command line arguments
	img_base_name:	str					=	None
	segments:		list[SegmentSpec]	=	field(default_factory=list)
	vid_dx:			int					=	-1	# in pixels
	vid_dy:			int					=	-1
	vid_fpms:		float				=	-1	# frames/ms
	vid_frames:		int					=	0
	vid_ms:			float				=	0	# in ms
	vid_s:			float				=	0	# in s

	# List of running processes
	proc_list:		list[subprocess.Popen] = field(default_factory=list)
# /class Globals

#***** Utility functions *******************************************************
def _DBG(dbgTxt) -> None:
	if glob.debug_mode:
		print(dbgTxt, end = '', flush = True)
	return
# /def _DBG


def _LOG(msg) -> None:
	print(msg, end = '', flush = True)
	return
# /def _DBG


# Visible whitespace - replace space, tab and newline with visible symbols
def _greySpace(txt: str) -> str:
	fromChars = ' \t\n'
	toChars = '\u2423\u21e5\u21b5'
	return txt.translate(str.maketrans(fromChars, toChars))
# /def _greySpace

#***** Other functions *********************************************************
def err_exit(msg: str = None) -> None:
	if msg is not None:
		print(msg)
	sys.exit(-1)

	# Never reached.
	return


def check_existance_infile() -> None:
	if not os.path.exists(glob.pcb_file):
		err_exit(term.err + "***ERROR*** kicad PCB file not found: " + term.errdata +
			"'" + glob.pcb_file + "'" + term.normal + "\n")
	else:
		return
# /def


def wait_available_thread_slots(at_least: int = 1) -> bool:
	def remove_returned() -> bool:
		retval = False
		for i in range(len(glob.proc_list)):
			po = glob.proc_list[i]
			poll_ret = po.poll()

			if poll_ret is None:		# Still running.
				pass
			else:
				glob.proc_list[i] = None# Mark removed in Popen list with placeholder None.
				if poll_ret == 0:		# Returned without error...
					pass				# ... do nothing.
				else:					# Returned with error.
					retval |= True		# Remember that at least one error has occured.
					stdout, stderr = po.communicate()	# Get output.
					_LOG(term.err + stdout + stderr + term.normal + "\n")
				# /if
			# /if


		while (None in glob.proc_list):	# Remove all None entries from process list.
			glob.proc_list.remove(None)
		return retval
	#/def remove_returned

	ret = remove_returned()
#	_LOG(term.title + "Busy wait... \n")
	while ((glob.max_threads - len(glob.proc_list)) < at_least):
		ret |= remove_returned()

	return ret
# /def wait_available_thread_slots


def run_thread(cmd: str, args: list) -> None:
	if len(glob.proc_list) > glob.max_threads:
		err_exit(term.error + "proc_list overflow\n")

	cmd_list = [cmd] + args

	try:
		glob.proc_list.append(subprocess.Popen(cmd_list,
												stdin = subprocess.PIPE,
												stdout = subprocess.PIPE,
												stderr = subprocess.PIPE,
												text = True))
	except OSError:
		raise		# Re-raise to function's caller.
	return
# /def run_thread

'''
Nåja, ett ännu bättre koncept än ≁GOTO är COMEFROM.

		...
		...
label:	...
		...
		...
		if (cond): COMEFROM label
		...
		...



'''
def parse_cmdline() -> None:
	def XY_size(XxY):
		if len(XxY) >= 3:
			if XxY.count("x") == 1:
				xylst = XxY.split("x")	# returns eg ["640", "480"]
				if xylst[0].isdigit() and xylst[1].isdigit():
					glob.vid_dx, glob.vid_dy = int(xylst[0]), int(xylst[1])
					return XxY
		raise argparse.ArgumentTypeError(f"must be e.g. 640x480")
	# /def

	parser = argparse.ArgumentParser(
		description='Parallellized PCB animation video creation by calling multiple kicad-cli-nightly instances to render the individual frames, then optionally joining the created image files to a video with ffmpeg.',
		allow_abbrev=False,	formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog='''


Multiple --segment args can be used. The resulting video will have them following each other in-order. The "from"-params of the 2nd segment should in that case be equal to the "toward"-params of the 1st, etc for continuous, seamless movement.

############### --segment "segm_expr" indepth ###############

Whitespace separating parts can be any length.

"1.3s	z(0.9) rot(1, 2, 3) pan(0,0,0) piv(0,0,0) -> \
		z(0.9) rot(4, 5, 6) pan(0,0,0) piv(0,0,0)"

Semiformal syntax description of segm_expr:

segm_expr	::= dur_expr WS from_expr WS "->" WS toward_expr
from_expr	::= toward_expr
toward_expr	::= [zoom_expr] [rot_expr] [pan_expr] [piv_expr]
dur_expr	::= floatnumber ("s" | "ms")
zoom_expr	::= "z" "(" floatnumber ")"
rot_expr	::= "rot" "(" [WS] rotax [WS] "," [WS] rotay [WS] "," [WS] rotaz [WS] ")"
pan_expr	::= "pan" "(" [WS] panax [WS] "," [WS] panay [WS] "," [WS] panaz [WS] ")"
piv_expr	::= "piv" "(" [WS] pivx [WS] "," [WS] pivy [WS] "," [WS] pivz [WS] ")"
rotax..z	::= floatnumber
panax..z	::= floatnumber
pivx..z		::= floatnumber
WS			::= (SP | TAB | NEWLINE)*

Animation is made by transitioning, using interpolation, in carefully calculated steps, the positional parameters from (from_expr) to (toward_expr) frame-by-frame. It's questionable if pivot animation is useful, but it can be, in the interest of flexibility.

(duration) is the target playing time of the animation segment. The animation segment will consist of (fps * duration in s) frames.

(zoom) is the camera zoomin. If absent, 1.0 is used.

(rotax, rotay, rotaz) define the PCBs rotation around the x,y,z-axii. If absent, (0,0,0) are used. kicad-cli-nightly seems to dislike angles outside the [-360..360] range, so don't use values outside this. TODO remainder division/normalize/direction arithmetic.

(panax, panay, panaz) define, if included, the viewpoint's panning.

(pivx, pivy, pivz) define, if included, the rotation pivot of the PCB in centimeters relative to its center.

############### Examples of segment expressions ###############
--segment "1500ms rot(0,0,0) -> rot(-180,30,45)"

equivalent generously fertilized with whitespace:
--segment "1.5s 	rot(0, 0, 0)  ->    rot(-180, 30,   45)"

With two segments, first a 2s slow rotation, then faster 1s one back to the video starting point:
--segment "2s	z(0.9)	rot(0,0,0)		 ->	z(0.9) rot(-180,30,45)" \
--segment "1s	z(0.9)	rot(-180,30,45)  ->	z(0.9) rot(0,0,0)"

Zoom in from afar while rotating:
--segment "3s z(0.1) rot(90,90,0) -> z(0.9) rot(0,0,0)"


'''									)

	parser.add_argument('-d', '--debug', action='store_true', dest='debug',
						help='debug mode')
	parser.add_argument('-nc', '--nocolor', '--nocolour', action='store_true', dest='nocolor',
						help='disable color output in terminal messages')
	parser.add_argument('-C', '--overwrite', action='store_true', dest='overwrite',
						help='overwrite existing images')
	parser.add_argument('--cli', type=str, metavar='</path/to/kicad-cli>',
						default='kicad-cli-nightly',
						help='kicad-cli executable (default: %(default)s)')

	parser.add_argument('--dry-run', action='store_true', dest='dry_run',
						help='go through all motions except modifying any files')

	parser.add_argument('--ffmpeg', type=str, metavar='</path/to/ffmpeg>',
						default='ffmpeg',
						help='ffmpeg executable (default: %(default)s)')
	parser.add_argument('--fps', type=int, metavar='<integer>',
						default=30, dest='fps',
						help='video framerate (default: %(default)d)')
	parser.add_argument('--img_format', type=str, metavar='jpg|png',
						default='png', choices=['jpg', 'png'],
						help='image format of frames (default: %(default)s)')
	parser.add_argument('-j', '--jobs', type=int, choices=range(1,9), metavar='<integer>',
						default=8,
						help='maximum number of concurrent jobs, [1..8] (default: %(default)d)')

	parser.add_argument('--out', type=str, metavar='<file>', dest='outfile', default=None,
						help='output video file, e.g. "video.mp4". If absent, the frames will be rendered but no video created')

	parser.add_argument('--tmpdir', type=str, metavar='<directory>',
						default='.',
						help='tmp file directory (default: %(default)s)')

	kc = parser.add_argument_group('options used when calling kicad-cli[-nightly]')
	kc.add_argument('--kc-background', dest='kc_background',
					type=str, metavar='transparent|opaque', default='transparent',
					choices=['transparent', 'opaque'],
					help='(default: %(default)s)')
	kc.add_argument('--kc-quality', dest='kc_quality',
					type=str, metavar='basic|high|user', default='high',
					choices=['basic', 'high', 'user'],
					help='(default: %(default)s)')
	kc.add_argument('--kc-preset', dest='kc_preset', default='follow_pcb_editor',
					type=str, metavar='<preset>',
					help='(default: %(default)s)')
	kc.add_argument('--kc-floor', action='store_true', dest='kc_floor',
					help='(default: not used)')
	kc.add_argument('--no-kc-perspective', dest='kc_perspective', action='store_true',
					help='do NOT use --perspective (default: %(default)s)')

	req = parser.add_argument_group('required arguments')

	req.add_argument('--in',
					nargs=1, metavar='<file>', dest='pcbfile', required=True,
					help='.kicad_pcb file')
	req.add_argument('--res',
					type=XY_size, metavar='<XxY>', nargs=1, required=True,
					help='target video resolution, e.g. 640x480')
	req.add_argument('-s', '--segment',
					type=str, metavar='<segm_expr>',
					action='append', dest='segments', required=True,
					help='add video segment. More than one --segment can be specified. See below for syntax.')

	args = parser.parse_args()


	glob.debug_mode		=	args.debug
	glob.dry_run		=	args.dry_run
	glob.ffmpeg_exe		=	args.ffmpeg
	glob.img_format		=	args.img_format
	glob.kc_background	=	args.kc_background
	glob.kc_floor		=	args.kc_floor
	glob.kc_perspective	=	not args.kc_perspective
	glob.kc_preset		=	args.kc_preset
	glob.kc_quality		=	args.kc_quality
	glob.kicad_cli_exe	=	args.cli
	glob.max_threads	=	args.jobs
	glob.nocolor		=	args.nocolor
	glob.out_file		=	args.outfile
	glob.overwrite		=	args.overwrite
	glob.pcb_file		=	args.pcbfile[0]
	glob.tmp_dir		=	args.tmpdir
	glob.vid_fps		=	args.fps
	glob.vid_res		=	args.res

	glob.img_base_name	=	os.path.join(glob.tmp_dir, os.path.basename(glob.pcb_file)) + ".FRAME_"
	glob.img_suffix		=	"." + glob.img_format
	glob.segment_args.extend(args.segments)
	glob.vid_fpms		=	glob.vid_fps / 1000

	if glob.nocolor:
		for field in dir(term):
			if not callable(getattr(term, field)) and not field.startswith("__"):
				setattr(term, field, "")

	return		# reached iff no illegal arguments
# /def parseArguments

# 2000 0.8 (0,0,0) 0.9 (30,40,50)

def segments_from_args() -> None:

	def triplex(s, seg_s) -> (float, float, float):
		tmp_lst = s.split(",")
		if len(tmp_lst) != 3:
			SYN_ERR(seg_s)
		try:
			x = float(tmp_lst[0])
			y = float(tmp_lst[1])
			z = float(tmp_lst[2])
		except Exception as e:
			SYN_ERR(str(e))
		return (x, y, z)
	#/def triplex

	def SYN_ERR(s) -> None:
		err_exit(term.err + "***ERROR*** Syntax: "+ term.errdata + s + "\n" + term.normal)
		return # Never reached
	#/def SYN_ERR


	for i in range(len(glob.segment_args)):
		_LOG(term.title +"Segment " + term.values + str(i) + term.title + ": \n")

		try:
			seg = SegmentSpec()
		except Exception as e:
			err_exit(term.err + "***ERROR*** WTF: " + term.errdata + str(e) + "\n" + term.normal)

		tmp_expr = ""
		tmp = glob.segment_args[i]

		tmp_lst = tmp.split(maxsplit = 1)
		if len(tmp_lst) < 2:
			SYN_ERR(glob.segment_args[i])
		else:
			if tmp_lst[0].endswith("ms"):
				div = 1000
			elif tmp_lst[0].endswith("s"):
				div = 1
			else:
				SYN_ERR(glob.segment_args[i])
			dur_s = tmp_lst[0].rstrip("sm")
			rest_s = tmp_lst[1]

#		_LOG(term.title + "dur_s, rest_s: " + term.values + "\"" + dur_s + "\", \"" +
#				rest_s + "\"\n")
		try:
			seg.dur = float(dur_s) / div
		except Exception as e:
			SYN_ERR(str(e))

#		_LOG(term.title + "dur = " + term.values + str(seg.dur) + "s\n")

		if rest_s.count("->") != 1:
			SYN_ERR(rest_s)
		else:
			(tmp_l_str , tmp_slask, tmp_r_str) = rest_s.partition("->")

#		expr_l_lst,	expr_r_lst	=	[], 					[]
		tmp_l_lst,	tmp_r_lst	=	tmp_l_str.split(")"),	tmp_r_str.split(")")
#		_LOG(term.title + "tmp_l_lst :" + term.values + str(tmp_l_lst) + "\n")
#		_LOG(term.title + "tmp_r_lst :" + term.values + str(tmp_r_lst) + "\n")

		l_incl_zoom = l_incl_rot = l_incl_pan = l_incl_piv = False


		for s in tmp_l_lst:
			snws = ''.join(s.split())
			if len(snws) > 0:
				if snws.startswith("z("):
					l_incl_zoom = True
					try:
						seg.fr_zoom = float(snws[2:])
					except Exception as e:
						SYN_ERR(str(e))
				elif snws.startswith("rot("):
					l_incl_rot = True
					(seg.fr_rotax,seg.fr_rotay,seg.fr_rotaz) = triplex(snws[4:], snws)
				elif snws.startswith("pan("):
					l_incl_pan = True
					(seg.fr_panax,seg.fr_panay,seg.fr_panaz) = triplex(snws[4:], snws)
				elif snws.startswith("piv("):
					l_incl_piv = True
					(seg.fr_pivx,seg.fr_pivy,seg.fr_pivz) = triplex(snws[4:], snws)
				else:
					SYN_ERR(glob.segment_args[i])
#				expr_l_lst.append(snws)
		for s in tmp_r_lst:
			snws = ''.join(s.split())
			if len(snws) > 0:
				if snws.startswith("z("):
					seg.incl_zoom = True
					try:
						seg.to_zoom = float(snws[2:])
					except Exception as e:
						SYN_ERR(str(e))
				elif snws.startswith("rot("):
					seg.incl_rot = True
					(seg.to_rotax,seg.to_rotay,seg.to_rotaz) = triplex(snws[4:], snws)
				elif snws.startswith("pan("):
					seg.incl_pan = True
					(seg.to_panax,seg.to_panay,seg.to_panaz) = triplex(snws[4:], snws)
				elif snws.startswith("piv("):
					seg.incl_piv = True
					(seg.to_pivx,seg.to_pivy,seg.to_pivz) = triplex(snws[4:], snws)
				else:
					SYN_ERR(glob.segment_args[i])
#				expr_r_lst.append(snws)
#		_LOG(term.title + "expr_l_lst :" + term.values + str(tmp_l_lst) + "\n")
#		_LOG(term.title + "expr_r_lst :" + term.values + str(tmp_r_lst) + "\n")
# x rot pan piv
#		_LOG(str(glob.vid_fps) + "\n")


		if ((seg.incl_zoom != l_incl_zoom) or (seg.incl_rot != l_incl_rot)
			or (seg.incl_pan != l_incl_pan) or (seg.incl_piv != l_incl_piv)):
			err_exit(term.err + "***ERROR*** Syntax: Terms from/toward mismatch\n" + term.normal)

		seg.frames = math.ceil(seg.dur * float(glob.vid_fps))

		# Interpolation step values
		seg.d_zoom	= (seg.to_zoom - seg.fr_zoom) / seg.frames
		seg.d_rotax	= (seg.to_rotax - seg.fr_rotax) / seg.frames
		seg.d_rotay	= (seg.to_rotay - seg.fr_rotay) / seg.frames
		seg.d_rotaz	= (seg.to_rotaz - seg.fr_rotaz) / seg.frames
		seg.d_panax	= (seg.to_panax - seg.fr_panax) / seg.frames
		seg.d_panay	= (seg.to_panay - seg.fr_panay) / seg.frames
		seg.d_panaz	= (seg.to_panaz - seg.fr_panaz) / seg.frames
		seg.d_pivx	= (seg.to_pivx - seg.fr_pivx) / seg.frames
		seg.d_pivy	= (seg.to_pivy - seg.fr_pivy) / seg.frames
		seg.d_pivz	= (seg.to_pivz - seg.fr_pivz) / seg.frames

#		_LOG(term.values + str(seg) + "\n" + term.normal)


		glob.segments.append(seg);
		glob.vid_ms += seg.dur * 1000
		glob.vid_s += seg.dur
		glob.vid_frames += seg.frames

		_LOG(term.title + "    duration " + term.values)
		_LOG(f"{seg.dur:.3f}" + term.title + "s (" + term.values)
		_LOG(f"{seg.frames}" + term.title + " frames)\n")

		if seg.incl_zoom:
			_LOG(term.title + "    zooming  " + term.values)
			_LOG(f"{seg.fr_zoom:.2f}" + term.title + " to " + term.values)
			_LOG(f"{seg.to_zoom:.2f}" + term.title + " step ≈ " + term.values)
			_LOG(f"{seg.d_zoom:.3f}" + "\n")

		if seg.incl_rot:
			_LOG(term.title + "    rotation (" + term.values)
			_LOG(f"{seg.fr_rotax:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.fr_rotay:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.fr_rotaz:.2f}" + term.title + ") to (" + term.values)
			_LOG(f"{seg.to_rotax:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.to_rotay:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.to_rotaz:.2f}" + term.title + ") step ≈(" + term.values)
			_LOG(f"{seg.d_rotax:.4f}" + term.title + ", " + term.values)
			_LOG(f"{seg.d_rotay:.4f}" + term.title + ", " + term.values)
			_LOG(f"{seg.d_rotaz:.4f}" + term.title + ")\n")

		if seg.incl_pan:
			_LOG(term.title + "    panning  (" + term.values)
			_LOG(f"{seg.fr_panax:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.fr_panay:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.fr_panaz:.2f}" + term.title + ") to (" + term.values)
			_LOG(f"{seg.to_panax:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.to_panay:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.to_panaz:.2f}" + term.title + ") step ≈(" + term.values)
			_LOG(f"{seg.d_panax:.4f}" + term.title + ", " + term.values)
			_LOG(f"{seg.d_panay:.4f}" + term.title + ", " + term.values)
			_LOG(f"{seg.d_panaz:.4f}" + term.title + ")\n")

		if seg.incl_piv:
			_LOG(term.title + "    pivoting (" + term.values)
			_LOG(f"{seg.fr_pivx:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.fr_pivy:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.fr_pivz:.2f}" + term.title + ") to (" + term.values)
			_LOG(f"{seg.to_pivx:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.to_pivy:.2f}" + term.title + ", " + term.values)
			_LOG(f"{seg.to_pivz:.2f}" + term.title + ") step ≈(" + term.values)
			_LOG(f"{seg.d_pivx:.4f}" + term.title + ", " + term.values)
			_LOG(f"{seg.d_pivy:.4f}" + term.title + ", " + term.values)
			_LOG(f"{seg.d_pivz:.4f}" + term.title + ")\n")

	_LOG(term.title + "Video: " + term.values + str(glob.vid_ms) + term.title + "ms (" +
		term.values + str(glob.vid_frames) + term.title + " frames) @ " + term.values +
		str(glob.vid_fps) + term.title + " FPS\n")

#	err_exit(term.title + "BREAK" + "\n" )
	return	# reached iff no errors
# /def parseSegments


def render_frames() -> None:
	# TODO	Make some of these configurable with cmdline args.
	cli_static_args	= ["pcb", "render"]

	frame_index = 0
	for seg_index in range(len(glob.segments)):
		seg = glob.segments[seg_index]
		zoom = seg.fr_zoom
		rotax, rotay, rotaz = seg.fr_rotax, seg.fr_rotay, seg.fr_rotaz
		panax, panay, panaz = seg.fr_panax, seg.fr_panay, seg.fr_panaz
		pivx, pivy, pivz = seg.fr_pivx, seg.fr_pivy, seg.fr_pivz

		for interseg_frame_index in range(seg.frames):
			wait_available_thread_slots(1)

			frame_filename = glob.img_base_name + f"{frame_index:06d}" + glob.img_suffix

			_LOG(term.title + "\nSegment " + term.values + f"{seg_index:3d}" + term.title +
					" frame " + term.values + f"{frame_index:4d}" + term.title + ", \"" +
					term.values + f"{frame_filename}" + term.title + "\" ... ")

			if os.path.exists(frame_filename):
				if not glob.overwrite:
					_LOG("skipped ")
					skip = True
				else:
					_LOG("re-rendering ")
					skip = False
			else:
				_LOG("rendering ")
				skip = False
			# /if


# -o tmp/img0001.jpg  ../../universellt_pcb/universellt_pcb.kicad_pcb
			#.............
			arglist = list()
			arglist.extend(cli_static_args)
			arglist.append("--rotate")
			arglist.append(f"{rotax:.2f},{rotay:.2f},{rotaz:.2f}")
			arglist.append("--zoom")
			arglist.append(f"{zoom:.3f}")
			if seg.incl_pan:
				arglist.append("--pan")
				arglist.append(f"{panax:.2f},{panay:.2f},{panaz:.2f}")
			if seg.incl_piv:
				arglist.append("--pivot")
				arglist.append(f"{pivx:.2f},{pivy:.2f},{pivz:.2f}")
			arglist.append("--width")
			arglist.append(f"{glob.vid_dx}")
			arglist.append("--height")
			arglist.append(f"{glob.vid_dy}")

			arglist.append("--background")
			arglist.append(glob.kc_background)
			if glob.kc_floor:
				arglist.append("--floor")
			if glob.kc_perspective:
				arglist.append("--perspective")
			arglist.append("--preset")
			arglist.append(glob.kc_preset)
			arglist.append("--quality")
			arglist.append(glob.kc_quality)

#	kc_background:	str			=	None
#	kc_floor:		bool		=	None
#	kc_perspective:	bool		=	None
#	kc_preset:		str			=	None
#	kc_quality:		str			=	None


			arglist.append("-o")
			arglist.append(f"{frame_filename}")
			arglist.append(glob.pcb_file)
			_DBG(term.values + str(arglist))
			if not skip:
#				pass
				if not glob.dry_run:
					run_thread(glob.kicad_cli_exe, arglist)

			zoom += seg.d_zoom
			rotax += seg.d_rotax
			rotay += seg.d_rotay
			rotaz += seg.d_rotaz
			panax += seg.d_panax
			panay += seg.d_panay
			panaz += seg.d_panaz
			pivx += seg.d_pivx
			pivy += seg.d_pivy
			pivz += seg.d_pivz

			frame_index += 1
	_LOG("\n")
	return


def create_video_file() -> None:
	# TODO	Make some of these configurable with cmdline args.
	ff_static_args_1 = ["-y", "-start_number", "0"]
	ff_static_args_2 = ["-c:v", "libx264", "-preset", "slow", "-crf", "22"]

	arglist = list()
	arglist.extend(ff_static_args_1)
	arglist.append("-framerate")
	arglist.append(f"{glob.vid_fps}")
	arglist.append("-i")
	arglist.append(glob.img_base_name + "%06d" + glob.img_suffix)
	arglist.extend(ff_static_args_2)
	arglist.append("-r")
	arglist.append(f"{glob.vid_fps}")
	arglist.append(glob.out_file)

	if not glob.dry_run:
		run_thread(glob.ffmpeg_exe, arglist)
	return
# /def create_video_file
#***** Main ********************************************************************

glob = Globals()

# I can't be bothered to find out which Python version is needed, so 3.7 is
# arbitrarily chosen.
if sys.hexversion < 0x03070000:		# bits 31..24: major, bits 23..16: minor
	err_exit(term.err + "***ERROR*** Python 3.7 or higher required. \n")


#_LOG(str(list(vars(term).keys())) + "\n")


#for field in dir(term):
#	if not callable(getattr(term, field)) and not field.startswith("__"):
#		print(field)

parse_cmdline()				# Returns IFF cmdline args seem mostly ok.

#_LOG(term.values + str(glob) + "\n")
#sys.exit(0)

#check_existance_infile()	# Returns IFF infile exists.

segments_from_args()		# Returns IFF all --segment specs check out syntactically ok.

_DBG(term.title + "\nGLOBALS " + term.extra + glob.__repr__() + '\n' + term.normal)

render_frames()

if wait_available_thread_slots(glob.max_threads):
	err_exit(term.err + "***ERROR*** at least one of the " + glob.kicad_cli_exe +
			" calls returned an error\n" + term.normal)

if glob.out_file != None:
	_LOG(term.title + "\nCreating video file... ")
	create_video_file()

if wait_available_thread_slots(glob.max_threads):
	err_exit(term.err + "***ERROR*** " + glob.ffmpeg_exe +
			" call returned error\n" + term.normal)


_LOG(" done\n")

sys.exit(0)

# ./anim_pcb.py -d --in ../../universellt_pcb/universellt_pcb.kicad_pcb --out bajs.mp4 --res 320x240 -C -s "500 0.8 (10,11,12) 1.0 (13,14,15)" -s "500 1.1 (20,21,22) 1.2 (23,24,25)"


# 2000 0.8 (0,0,0) 0.9 (30,40,50)
#
# Segment syntax:
# "int float (int,int,int) float (int,int,int)"
# "dur zoom1 (ax1,ay1,az1) zoom2 (ax2,ay2,az2)"
#
# Animated video segment dur milliseconds long from a rotation of ax1,ay1,az1 at a zoom of zoom1
# to a rotation of ax2,ay2,az2 at a zoom of zoom2. Angles must be within -359..359.
#
# Example segment: --segment "1000 0.9 (0,0,0) 1.0 (10,120,240)"
#
#
# mkdir -p tmp && kicad-cli-nightly pcb render --preset follow_pcb_editor --quality basic --perspective --rotate "0,0,0" --zoom 0.8 -w 320 -h 240 --background opaque -o tmp/img0001.jpg  ../../universellt_pcb/universellt_pcb.kicad_pcb


#--rotate "0,0,0" --zoom 0.8 -w 320 -h 240 --background opaque -o tmp/img0001.jpg  ../../universellt_pcb/universellt_pcb.kicad_pcb

#
# 	0		0		0		rakt uppifrån, "icke-roterat"
# 	x		0		0		rot runt kortets horisontella axel, medurs sett från vänstra sidan
#	0		y		0		rot runt kortets vertikala axel, medurs sett från underkanten
#	0		0		z		rot runt kortets normal, medurs sett underifrån (!)
#
#

# "Emulsified high-fat offal tube"
