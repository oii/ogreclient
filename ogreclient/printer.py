from __future__ import absolute_import
from __future__ import unicode_literals

import datetime
import logging
import sys
import threading
import traceback

PROGBAR_LEN = 40


class CliPrinter(object):
    '''
    Singleton-style factory class

    The python magic methods below forward dir/get/set calls onto the underlying
    _prntr object (as Python's Logger class).
    '''
    _prntr = None

    def __init__(self):
        if not CliPrinter._prntr:
            CliPrinter.init()

    def __getattribute__(self, name):
        return getattr(CliPrinter._prntr, name)

    def __setattr__(self, name, value):
        return setattr(CliPrinter._prntr, name, value)

    def __dir__(self):
        return dir(self._prntr)

    @classmethod
    def get_printer(cls):
        return CliPrinter()

    @classmethod
    def init(cls, *args, **kwargs):
        if kwargs.get('quiet'):
            cls._prntr = DummyPrinter()
        else:
            if 'quiet' in kwargs:
                del(kwargs['quiet'])
            cls._prntr = CliPrinterImpl(*args, **kwargs)


class CliPrinterImpl:
    class Colours:
        nocolour = False
        _default = None

        @property
        def default(self):
            return self._default or self.NORMAL

        @default.setter
        def default(self, val):
            self._default = val

        def __getattr__(self, key):
            if self.nocolour:
                return ''
            _colours = {
                'NORMAL': '\033[37m',
                'WHITE': '\033[97m',
                'CYAN': '\033[96m',
                'MAGENTA': '\033[95m',
                'BLUE': '\033[94m',
                'YELLOW': '\033[93m',
                'GREEN': '\033[92m',
                'RED': '\033[91m',
                'GREY': '\033[90m',
                'END': '\033[0m',
            }
            try:
                return _colours[key]
            except KeyError:
                raise AttributeError

    colours = Colours()

    TAB_SIZE = 4

    log_output = False
    logs = []

    def __init__(self, level=False, app_name=None, use_prefix=False,
                 progressbar_len=PROGBAR_LEN, progressbar_char="#",
                 notimer=False, nocolour=True, default_colour=None, log_output=False):

        if use_prefix is True and app_name is None:
            raise IllegalArgumentError('You must supply app_name when use_prefix is True')

        # validate logging.level
        if not level:
            self.level = logging.INFO
        else:
            self.level = logging._checkLevel(level)
        self.app_name = app_name
        self.use_prefix = use_prefix
        self.notimer = notimer
        self.progressbar_len = progressbar_len
        self.progressbar_char = progressbar_char
        self.colours.nocolour = nocolour
        self.colours.default = default_colour
        self.log_output = log_output

        # start the timer if it's in use
        if notimer is False:
            self.start = datetime.datetime.now()

        # used internally for tracking state
        self.progress_running = False
        self.line_needs_finishing = False
        self.infinite_progress_state = None

        # create a mutex for thread-safe printing
        self.lock = threading.Lock()


    @staticmethod
    def _get_colour(success=None, bold=False):
        colour = CliPrinterImpl.colours.default or CliPrinterImpl.colours.NORMAL

        if bold:
            colour = CliPrinterImpl.colours.WHITE

        if success is True:
            colour = CliPrinterImpl.colours.GREEN
        elif success is False:
            colour = CliPrinterImpl.colours.RED

        return colour

    def _get_prefix(self, prefix):
        prefix = ''

        if self.use_prefix is True:
            prefix = '[{: <10}] '.format(prefix.upper() or self.app_name.upper())

        return prefix


    def debug(self, *args, **kwargs):
        if self.level <= logging.DEBUG:
            self.p(*args, **kwargs)

    def info(self, *args, **kwargs):
        if self.level <= logging.INFO:
            self.p(*args, **kwargs)

    def warning(self, *args, **kwargs):
        if self.level <= logging.WARNING:
            self.p(*args, **kwargs)

    def critical(self, *args, **kwargs):
        if self.level <= logging.CRITICAL:
            self.e(*args, **kwargs)


    def error(self, msg=None, prefix=None, excp=None, notime=False):
        if msg is None and excp is None:
            raise IllegalArgumentError('You must supply either msg or excp')

        if excp:
            # format the exception object into printables
            excp_msg, inner_msg, traceback = self.format_excp(excp)

            if self.level == logging.DEBUG:
                self.p(excp_msg, prefix, success=False, notime=notime, extra=traceback)
            else:
                # display supplied friendly message, or print exception message
                if not msg:
                    msg = excp_msg
                else:
                    extra = str(excp)

                self.p(msg, prefix, success=False, notime=notime, extra=extra or inner_msg)
        else:
            self.p(msg, prefix, success=False, notime=notime)


    def p(self, msg, prefix=None, notime=False, success=None, extra=None, nonl=False, tabular=False, bold=False):
        # print a newline if required (this also ends any active progress bars)
        self.print_newline()

        # setup for print
        colour = CliPrinterImpl._get_colour(success=success, bold=bold)
        prefix = self._get_prefix(prefix)

        # default stdout
        out = sys.stdout

        if success is False:
            out = sys.stderr

        # log all prints to a stack for later use
        if self.log_output is True:
            self.logs.append('{}  {}'.format(prefix, msg))

        if self.start is None:
            notime = True

        # calculate and format elapsed time
        t = self._get_time_elapsed(notime)

        # format tabular data
        if tabular is True and type(msg) is list:
            msg = self._format_tabular(msg)

        # thread-safe printing to stdout
        with self.lock:
            out.write('{}{}{}{}{}{}'.format(
                prefix, CliPrinterImpl.colours.GREY,
                t, colour, msg, CliPrinterImpl.colours.END
            ))

            # handle multi-line extra text, display it nicely
            if extra is not None and isinstance(extra, basestring):
                if '\n' in extra:
                    extra = extra.split('\n')

            if type(extra) is list:
                for line in extra:
                    out.write('\n{}> {}{}'.format(
                        prefix, CliPrinterImpl.colours.END, line
                    ))
            elif extra is not None:
                out.write('\n{}> {}{}'.format(
                    prefix, CliPrinterImpl.colours.END, extra
                ))

            if nonl is True:
                self.line_needs_finishing = True
            else:
                out.write('\n')

            out.flush()


    def progressi(self, prefix=None, notime=False):
        if self.level > logging.INFO:
            return

        colour = CliPrinterImpl._get_colour()
        prefix = self._get_prefix(prefix)

        self.progress_running = True

        # start or reset the infinite progress counter
        if not self.infinite_progress_state or self.infinite_progress_state == 4:
            self.infinite_progress_state = 0

        PROG_CHARS = ['|', '/', '-', '\\']

        t = self._get_time_elapsed(notime)
        sys.stdout.write('\r{}{}{}{}[ {} ]{}'.format(
            prefix, CliPrinterImpl.colours.GREY, t, colour,
            PROG_CHARS[self.infinite_progress_state] * self.progressbar_len,
            CliPrinterImpl.colours.END
        ))
        sys.stdout.flush()

        self.infinite_progress_state += 1


    def progressf(self, num_blocks=None, block_size=1, total_size=None, extra=None, notime=False, prefix=None):
        if self.level > logging.INFO:
            return

        if num_blocks is None or total_size is None:
            raise ProgressfArgumentError

        if extra is None:
            extra = ''

        self.progress_running = True

        colour = CliPrinterImpl._get_colour()
        prefix = self._get_prefix(prefix)

        # calculate progress bar size
        progress = float(num_blocks * block_size) / float(total_size)
        progress = progress if progress < 1 else 1

        t = self._get_time_elapsed(notime)
        sys.stdout.write('\r{}{}{}{}[ {}{} ] {}%{}'.format(
            prefix, CliPrinterImpl.colours.GREY, t, colour,
            self.progressbar_char * int(progress * self.progressbar_len),
            ' ' * (self.progressbar_len - int(progress * self.progressbar_len)),
            round(progress * 100, 1),
            CliPrinterImpl.colours.GREY, extra,
            CliPrinterImpl.colours.END
        ))
        sys.stdout.flush()


    def end_progress(self):
        # end progress bar by displaying 100%
        if self.progress_running is True:
            self.infinite_progress_state = None
            self.progressf(1, 1, 1)


    def _get_time_elapsed(self, notime=False, formatted=True):
        if self.notimer is True or notime is True:
            return ''

        ts = datetime.datetime.now() - self.start
        if formatted is True:
            formatted_ts = '{:02}:{:02}:{:02}'.format(
                ts.seconds // 3600,
                ts.seconds % 3600 // 60,
                ts.seconds % 60
            )
            # return formatted time with space padding
            return '{: <4} '.format(formatted_ts)
        else:
            return ts


    def _format_tabular(self, data):
        column_tab_sizes = {}

        # iterate columns
        for colindex in range(len(data[0])):
            # get the longest string in this column
            len_max_string = max(len(str(row[colindex])) for row in data)
            # calculate the number of tabs required
            num_tabs = 1
            while len_max_string - (CliPrinterImpl.TAB_SIZE * num_tabs) > 0:
                num_tabs += 1
            # store for later
            column_tab_sizes[colindex] = num_tabs

        # assume the first item in the list is the table header
        header_row = data.pop(0)

        # create table header
        header = ''
        for colindex in range(len(header_row)):
            header += '| {}{}'.format(
                header_row[colindex],
                self._get_padding(header_row[colindex], column_tab_sizes[colindex])
            )

        # create table separator
        separator = '+{}\n'.format(len(header) * '-')

        table = ''
        for row in data:
            # check for separator row
            sep = True
            for item in row:
                if item != '-':
                    sep = False
                    break
            if sep is True:
                table += separator
                continue

            # output rows
            for colindex in range(len(row)):
                table += '| {}{}'.format(
                    row[colindex],
                    self._get_padding(row[colindex], column_tab_sizes[colindex])
                )
            table += '\n'

        # compose table and remove trailing newline
        return '\n{0}{1}\n{0}{2}{0}'.format(separator, header, table)[:-1]

    def _get_padding(self, word, num_tabs):
        return ' ' * ((CliPrinterImpl.TAB_SIZE * num_tabs) - len(str(word)))


    def format_excp(self, ex):
        """
        Accepts an exception object and returns a tuple of message, inner_message,
        if available and a formatted stacktrace
        """
        msg = '{}: {}'.format(ex.__class__.__name__, ex)
        inner_msg = ''
        stacktrace = ''

        if hasattr(ex, 'inner_excp') and isinstance(ex.inner_excp, Exception):
            inner_msg = unicode(ex.inner_excp)

        if self.level == logging.DEBUG:
            # extract and print the latest exception; which is good for printing
            # immediately when the exception occurs
            _, _, tb = sys.exc_info()
            if tb is not None:
                stacktrace += ''.join(traceback.format_tb(tb))[:-1]

            # the ex.inner_excp from CoreException mechanism provides a way to
            # wrap a lower exception in a meaningful application specific one
            if hasattr(ex, 'inner_excp') and isinstance(ex.inner_excp, Exception):
                stacktrace += '\nInner Exception:\n  {}: {}\n'.format(
                    ex.inner_excp.__class__.__name__, ex.inner_excp
                )
                if hasattr(ex, 'inner_traceback') and ex.inner_traceback is not None:
                    stacktrace += ex.inner_traceback

        return msg, inner_msg, stacktrace

    def close(self):
        self.end_progress()
        self.print_newline()

    def print_newline(self):
        with self.lock:
            if self.line_needs_finishing is True or self.progress_running is True:
                self.progress_running = False
                self.line_needs_finishing = False
                sys.stdout.write('\n')
                sys.stdout.flush()


class DummyPrinter:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def critical(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def progressi(self, *args, **kwargs):
        pass

    def progressf(self, *args, **kwargs):
        pass

    def close(self):
        pass


class IllegalArgumentError(ValueError):
    pass


class ProgressfArgumentError(IllegalArgumentError):
    def __init__(self):
        super(ProgressfArgumentError, self).__init__(
            'You must supply num_blocks and total_size'
        )


class CoreException(Exception):
    def __init__(self, message=None, inner_excp=None):
        super(CoreException, self).__init__(message)
        self.inner_excp = inner_excp

        # extract traceback from inner_excp
        if inner_excp is not None:
            # this is not guaranteed to work since sys.exc_info() gets only
            # the _most recent_ exception
            _, _, tb = sys.exc_info()
            if tb is not None:
                self.inner_traceback = ''.join(traceback.format_tb(tb))[:-1]
