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
	dur:		int		=	-1
	frames:		int		=	-1
	fr_zoom:	float	=	-1
	fr_ax:		float	=	-1
	fr_ay:		float	=	-1
	fr_az:		float	=	-1
	to_zoom:	float	=	-1
	to_ax:		float	=	-1
	to_ay:		float	=	-1
	to_az:		float	=	-1
	step_zoom:	float	=	-1
	step_ax:	float	=	-1
	step_ay:	float	=	-1
	step_az:	float	=	-1
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
	kc_pivot:		str			=	None
	kc_preset:		str			=	None
	kc_quality:		str			=	None
	kicad_cli_exe:	str			=	None
	nocolor:		bool		=	None
	overwrite:		bool		=	None
	debug_mode:		bool		=	None
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
	vid_fpms:		float				=	-1
	vid_frames:		int					=	0	# frames/ms
	vid_ms:			int					=	0	# in ms

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
		description='Parallellized PCB animation video creation by calling multiple kicad-cli-nightly instances to make the individual frames, then joining them to a video with ffmpeg.',
		allow_abbrev=False,	formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog='''


******************************************************************************
Animation segment expression segm_expr (as expected by the --segment arg):

segm_expr	::= duration ("s" | "ms") SEP from_expr TRFORM_SEP toward_expr
from_expr	::= toward_expr
toward_expr	::= zoom SEP rot_expr [SEP pan_expr]
rot_expr	::= rotax SEP rotay SEP rotaz
pan_expr	::= panax SEP panay SEP panaz
duration	::= floatnumber
rotax		::= floatnumber
rotay		::= floatnumber
rotaz		::= floatnumber
panax		::= floatnumber
panay		::= floatnumber
panaz		::= floatnumber
TRFORM_SEP	::= [ign_chars] "->" [ign_chars]
SEP			::= [ign_chars] "," [ign_chars]
ign_chars	::= (SP | TAB | NEWLINE | "(" | ")" | "[" | "]" | "{" | "}")*

Whitespace and "()[]{}" are stripped before parsing the --segment strings, so these can be used to e.g. group the parameters, as reading aids for ease-of-overview.

(rotax, rotay, rotaz) define the PCBs rotation around the x,y,z-axii.
(panax, panay, panaz), if included, define the viewpoint's panning. Not really tested extensivatall.
(duration) is the target playing time of the animation segment. The animation segment will consist of (fps * duration in s) frames.
(zoom) is the camera zoomin.
kicad_cli seems to dislike angles outside the [-360..360] range, so keep within. I should probably do a remainder division thing in the future.

Multiple --segment args can be used. The resulting video will have them following each other in-order. The "from"-params of the 2nd segment should be equal to the "toward"-params of the 1st, etc for continuous, seamless rotation.

Examples:
--segment "1500ms,1.0,0,0,0->1.0,-180,30,45"

equivalent with reading aids:
--segment "1.5s,	1.0,	(0,0,0) -> 1.0, (-180,30,45)"

With two segments, first a 2s slow rotation, then faster 1s one back to the video starting point:
--segment "2s,0.9,(0,0,0)->0.9,(-180,30,45)" --segment "1s,0.9,(-180,30,45)->0.9,(0,0,0)"

Zoom in from afar while rotating:
--segment "3s,0.1,(90,90,0)->0.9,(0,0,0)"


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
	parser.add_argument('--ffmpeg', type=str, metavar='</path/to/ffmpeg>',
						default='ffmpeg',
						help='ffmpeg executable (default: %(default)s)')
	parser.add_argument('--fps', type=int, metavar='<integer>',
						default=30,
						help='video framerate (default: %(default)d)')
	parser.add_argument('--img_format', type=str, metavar='jpg|png',
						default='png', choices=['jpg', 'png'],
						help='image format of frames (default: %(default)s)')
	parser.add_argument('-j', '--jobs', type=int, choices=range(1,9), metavar='<integer>',
						default=8,
						help='maximum number of concurrent jobs, [1..8] (default: %(default)d)')
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
	kc.add_argument('--kc-pivot', dest='kc_pivot', default='',
					type=str, metavar='<pivot>',
					help='(default: not used)')

	req = parser.add_argument_group('required arguments')

	req.add_argument('--in',
					nargs=1, metavar='<file>', dest='pcbfile', required=True,
					help='.kicad_pcb file')
	req.add_argument('--out',
					nargs=1, metavar='<file>', dest='outfile', required=True,
					help='output video file, e.g. video.mp4')
	req.add_argument('--res',
					type=XY_size, metavar='<XxY>', nargs=1, required=True,
					help='target video resolution, e.g. 640x480')
	req.add_argument('-s', '--segment',
					type=str, metavar='<segm_expr>',
					action='append', dest='segments', required=True,
					help='add video segment. More than one --segment can be specified. See below for syntax.')

	args = parser.parse_args()


	glob.debug_mode		=	args.debug
	glob.ffmpeg_exe		=	args.ffmpeg
	glob.img_format		=	args.img_format
	glob.kc_background	=	args.kc_background
	glob.kc_floor		=	args.kc_floor
	glob.kc_perspective	=	not args.kc_perspective
	glob.kc_pivot		=	args.kc_pivot
	glob.kc_preset		=	args.kc_preset
	glob.kc_quality		=	args.kc_quality
	glob.kicad_cli_exe	=	args.cli
	glob.max_threads	=	args.jobs
	glob.nocolor		=	args.nocolor
	glob.out_file		=	args.outfile[0]
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
	for i in range(len(glob.segment_args)):
		_LOG(term.title + "Segment " + str(i) + ": ")
		arg = glob.segment_args[i]
		arg_words = arg.split()
		if len(arg_words) != 5:
				err_exit(term.err + "***ERROR*** Syntax: " + term.errdata + arg + "\n")
		tuple1_word = arg_words[2].removeprefix("(").removesuffix(")")
		tuple2_word = arg_words[4].removeprefix("(").removesuffix(")")
		tuple1_vals = tuple1_word.split(",")
		tuple2_vals = tuple2_word.split(",")
		if (len(tuple1_vals) != 3) or (len(tuple2_vals) != 3):
				err_exit(term.err + "***ERROR*** Syntax: " + term.errdata + arg + "\n")
#		if len(tuple2_vals) != 3:
#				print(term.err + "***ERROR*** Syntax: " + arg + "\n")
#				sys.exit(0)

		try:
			seg = SegmentSpec(
						dur		=	int(arg_words[0]),
						frames	=	int(float(int(arg_words[0])) * glob.vid_fpms),
						fr_zoom	=	float(arg_words[1]),
						to_zoom	=	float(arg_words[3]),
						fr_ax	=	float(tuple1_vals[0]),
						fr_ay	=	float(tuple1_vals[1]),
						fr_az	=	float(tuple1_vals[2]),
						to_ax	=	float(tuple2_vals[0]),
						to_ay	=	float(tuple2_vals[1]),
						to_az	=	float(tuple2_vals[2]),
				)
		except Exception as e:
			err_exit(term.err + "***ERROR*** Syntax: " + str(e) + " " + term.errdata +
					"\"" + arg + "\"\n" + term.normal)

		seg.step_ax		= (seg.to_ax - seg.fr_ax) / float(seg.frames)
		seg.step_ay		= (seg.to_ay - seg.fr_ay) / float(seg.frames)
		seg.step_az		= (seg.to_az - seg.fr_az) / float(seg.frames)
		seg.step_zoom	= (seg.to_zoom - seg.fr_zoom) / float(seg.frames)
		glob.segments.append(seg);
		glob.vid_ms += seg.dur
		glob.vid_frames += int(float(seg.dur) * glob.vid_fpms)

		_LOG(term.values +
				"\tdur="					+	f"{seg.dur}"			+
				", frames="					+	f"{seg.frames}"			+
				"\n\t\tstart\t(fr_zoom≈"	+	f"{seg.fr_zoom:.2f}"	+
				", fr_ax="					+	f"{seg.fr_ax:.2f}"		+
				", fr_ay≈"					+	f"{seg.fr_ay:.2f}"		+
				", fr_az≈"					+	f"{seg.fr_az:.2f}"		+
				")\n\t\tend\t(to_zoom≈"		+	f"{seg.to_zoom:.2f}"	+
				", to_ax≈"					+	f"{seg.to_ax:.2f}"		+
				", to_ay≈"					+	f"{seg.to_ay:.2f}"		+
				", to_az≈"					+	f"{seg.to_az:.2f}"		+
				")\n\t\tsteps\t(step_zoom≈"	+	f"{seg.step_zoom:.2f}"	+
				", step_ax≈"				+	f"{seg.step_ax:.2f}"	+
				", step_ay≈"				+	f"{seg.step_ay:.2f}"	+
				", step_az≈"				+	f"{seg.step_az:.2f}" 	+	")"	+
				term.normal + "\n")

	_LOG(term.title + "Video: " + term.values + str(glob.vid_frames) + " frames total, duration "
			+ str(glob.vid_ms) + "ms @ " + str(glob.vid_fps) + " FPS" + term.normal + "\n")
	return
# /def parseSegments


def render_frames() -> None:
	# TODO	Make some of these configurable with cmdline args.
	cli_static_args	= ["pcb", "render", "--preset", "follow_pcb_editor", "--quality", "high",
						"--floor", "--perspective", "--background", "transparent"]

	frame_index = 0
	for seg_index in range(len(glob.segments)):
		seg = glob.segments[seg_index]
		ax = seg.fr_ax
		ay = seg.fr_ay
		az = seg.fr_az
		zoom = seg.fr_zoom

		for interseg_frame_index in range(seg.frames):
			wait_available_thread_slots(1)

			frame_filename = glob.img_base_name + f"{frame_index:06d}" + glob.img_suffix

			_LOG(term.title + "\nSegment " + term.values + f"{seg_index:3d}" + term.title +
					" frame " + term.values + f"{frame_index:4d}" + term.title + ", \"..." +
					term.values + f"{frame_index:06d}" + glob.img_suffix + term.title + "\" ... ")

			if os.path.exists(frame_filename):
				if not glob.clobber:
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
			arglist.append(f"{ax:.2f},{ay:.2f},{az:.2f}")
			arglist.append("--zoom")
			arglist.append(f"{zoom:.3f}")
			arglist.append("-w")
			arglist.append(f"{glob.vid_dx}")
			arglist.append("-h")
			arglist.append(f"{glob.vid_dy}")
			arglist.append("-o")
			arglist.append(f"{frame_filename}")
			arglist.append(glob.pcb_file)
			_DBG(term.values + str(arglist))
			if not skip:
#				pass
				run_thread(glob.kicad_cli_exe, arglist)

			ax += seg.step_ax
			ay += seg.step_ay
			az += seg.step_az
			zoom += seg.step_zoom
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

_LOG(term.values + str(glob) + "\n")
sys.exit(0)

check_existance_infile()	# Returns IFF infile exists.

segments_from_args()		# Returns IFF all --segment specs check out syntactically ok.

_DBG(term.title + "\nGLOBALS " + term.extra + glob.__repr__() + '\n' + term.normal)

render_frames()

if wait_available_thread_slots(glob.max_threads):
	err_exit(term.err + "***ERROR*** at least one of the " + glob.kicad_cli_exe +
			" calls returned an error\n" + term.normal)

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
