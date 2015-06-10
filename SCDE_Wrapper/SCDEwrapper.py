# SCDEwrapper/SCDEwrapper.py - a self annotated version of rgToolFactory.py generated by running rgToolFactory.py
# to make a new Galaxy tool called SCDEwrapper
# User admin@galaxy.org at 16/04/2015 10:09:46
# rgToolFactory.py
# see https://bitbucket.org/fubar/galaxytoolfactory/wiki/Home
# 
# copyright ross lazarus (ross stop lazarus at gmail stop com) May 2012
# 
# all rights reserved
# Licensed under the LGPL
# suggestions for improvement and bug fixes welcome at https://bitbucket.org/fubar/galaxytoolfactory/wiki/Home
#
# August 2014 
# merged John Chilton's citation addition and ideas from Marius van den Beek to enable arbitrary
# data types for input and output - thanks!
#
# march 2014
# had to remove dependencies because cross toolshed dependencies are not possible - can't pre-specify a toolshed url for graphicsmagick and ghostscript
# grrrrr - night before a demo
# added dependencies to a tool_dependencies.xml if html page generated so generated tool is properly portable
#
# added ghostscript and graphicsmagick as dependencies 
# fixed a wierd problem where gs was trying to use the new_files_path from universe (database/tmp) as ./database/tmp
# errors ensued
#
# august 2013
# found a problem with GS if $TMP or $TEMP missing - now inject /tmp and warn
#
# july 2013
# added ability to combine images and individual log files into html output
# just make sure there's a log file foo.log and it will be output
# together with all images named like "foo_*.pdf
# otherwise old format for html
#
# January 2013
# problem pointed out by Carlos Borroto
# added escaping for <>$ - thought I did that ages ago...
#
# August 11 2012 
# changed to use shell=False and cl as a sequence

# This is a Galaxy tool factory for simple scripts in python, R or whatever ails ye.
# It also serves as the wrapper for the new tool.
# 
# you paste and run your script
# Only works for simple scripts that read one input from the history.
# Optionally can write one new history dataset,
# and optionally collect any number of outputs into links on an autogenerated HTML page.

# DO NOT install on a public or important site - please.

# installed generated tools are fine if the script is safe.
# They just run normally and their user cannot do anything unusually insecure
# but please, practice safe toolshed.
# Read the fucking code before you install any tool 
# especially this one

# After you get the script working on some test data, you can
# optionally generate a toolshed compatible gzip file
# containing your script safely wrapped as an ordinary Galaxy script in your local toolshed for
# safe and largely automated installation in a production Galaxy.

# If you opt for an HTML output, you get all the script outputs arranged
# as a single Html history item - all output files are linked, thumbnails for all the pdfs.
# Ugly but really inexpensive.
# 
# Patches appreciated please. 
#
#
# long route to June 2012 product
# Behold the awesome power of Galaxy and the toolshed with the tool factory to bind them
# derived from an integrated script model  
# called rgBaseScriptWrapper.py
# Note to the unwary:
#   This tool allows arbitrary scripting on your Galaxy as the Galaxy user
#   There is nothing stopping a malicious user doing whatever they choose
#   Extremely dangerous!!
#   Totally insecure. So, trusted users only
#
# preferred model is a developer using their throw away workstation instance - ie a private site.
# no real risk. The universe_wsgi.ini admin_users string is checked - only admin users are permitted to run this tool.
#

import sys 
import shutil 
import subprocess 
import os 
import time 
import tempfile 
import optparse
import tarfile
import re
import shutil
import math

progname = os.path.split(sys.argv[0])[1] 
myversion = 'V001.1 March 2014' 
verbose = False 
debug = False
toolFactoryURL = 'https://bitbucket.org/fubar/galaxytoolfactory'

# if we do html we need these dependencies specified in a tool_dependencies.xml file and referred to in the generated
# tool xml
toolhtmldepskel = """<?xml version="1.0"?>
<tool_dependency>
    <package name="ghostscript" version="9.10">
        <repository name="package_ghostscript_9_10" owner="devteam" prior_installation_required="True" />
    </package>
    <package name="graphicsmagick" version="1.3.18">
        <repository name="package_graphicsmagick_1_3" owner="iuc" prior_installation_required="True" />
    </package>
        <readme>
           %s
       </readme>
</tool_dependency>
"""

protorequirements = """<requirements>
      <requirement type="package" version="9.10">ghostscript</requirement>
      <requirement type="package" version="1.3.18">graphicsmagick</requirement>
  </requirements>"""

def timenow():
    """return current time as a string
    """
    return time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(time.time()))

html_escape_table = {
     "&": "&amp;",
     ">": "&gt;",
     "<": "&lt;",
     "$": "\$"
     }

def html_escape(text):
     """Produce entities within text."""
     return "".join(html_escape_table.get(c,c) for c in text)

def cmd_exists(cmd):
     return subprocess.call("type " + cmd, shell=True, 
           stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0


def parse_citations(citations_text):
    """
    """
    citations = [c for c in citations_text.split("**ENTRY**") if c.strip()]
    citation_tuples = []
    for citation in citations:
        if citation.startswith("doi"):
            citation_tuples.append( ("doi", citation[len("doi"):].strip() ) )
        else:
            citation_tuples.append( ("bibtex", citation[len("bibtex"):].strip() ) )
    return citation_tuples


class ScriptRunner:
    """class is a wrapper for an arbitrary script
    """

    def __init__(self,opts=None,treatbashSpecial=True):
        """
        cleanup inputs, setup some outputs
        
        """
        self.useGM = cmd_exists('gm')
        self.useIM = cmd_exists('convert')
        self.useGS = cmd_exists('gs')
        self.temp_warned = False # we want only one warning if $TMP not set
        self.treatbashSpecial = treatbashSpecial
        if opts.output_dir: # simplify for the tool tarball
            os.chdir(opts.output_dir)
        self.thumbformat = 'png'
        self.opts = opts
        self.toolname = re.sub('[^a-zA-Z0-9_]+', '', opts.tool_name) # a sanitizer now does this but..
        self.toolid = self.toolname
        self.myname = sys.argv[0] # get our name because we write ourselves out as a tool later
        self.pyfile = self.myname # crude but efficient - the cruft won't hurt much
        self.xmlfile = '%s.xml' % self.toolname
        s = open(self.opts.script_path,'r').readlines()
        s = [x.rstrip() for x in s] # remove pesky dos line endings if needed
        self.script = '\n'.join(s)
        fhandle,self.sfile = tempfile.mkstemp(prefix=self.toolname,suffix=".%s" % (opts.interpreter))
        tscript = open(self.sfile,'w') # use self.sfile as script source for Popen
        tscript.write(self.script)
        tscript.close()
        self.indentedScript = '\n'.join([' %s' % html_escape(x) for x in s]) # for restructured text in help
        self.escapedScript = '\n'.join([html_escape(x) for x in s])
        self.elog = os.path.join(self.opts.output_dir,"%s_error.log" % self.toolname)
        if opts.output_dir: # may not want these complexities 
            self.tlog = os.path.join(self.opts.output_dir,"%s_runner.log" % self.toolname)
            art = '%s.%s' % (self.toolname,opts.interpreter)
            artpath = os.path.join(self.opts.output_dir,art) # need full path
            artifact = open(artpath,'w') # use self.sfile as script source for Popen
            artifact.write(self.script)
            artifact.close()
        self.cl = []
        self.html = []
        a = self.cl.append
        a(opts.interpreter)
        if self.treatbashSpecial and opts.interpreter in ['bash','sh']:
            a(self.sfile)
        else:
            a('-') # stdin
        a(opts.input_tab)
        a(opts.output_tab)
        a(opts.notuse_flex)
        a(opts.dropout_base)
        a(opts.failed_base)
        a(opts.count_fpkm)
        self.outputFormat = self.opts.output_format
        self.inputFormats = self.opts.input_formats 
        self.test1Input = '%s_test1_input.xls' % self.toolname
        self.test1Output = '%s_test1_output.xls' % self.toolname
        self.test1HTML = '%s_test1_output.html' % self.toolname

    def makeXML(self):
        """
        Create a Galaxy xml tool wrapper for the new script as a string to write out
        fixme - use templating or something less fugly than this example of what we produce

        <tool id="reverse" name="reverse" version="0.01">
            <description>a tabular file</description>
            <command interpreter="python">
            reverse.py --script_path "$runMe" --interpreter "python" 
            --tool_name "reverse" --input_tab "$input1" --output_tab "$tab_file" 
            </command>
            <inputs>
            <param name="input1"  type="data" format="tabular" label="Select a suitable input file from your history"/><param name="job_name" type="text" label="Supply a name for the outputs to remind you what they contain" value="reverse"/>

            </inputs>
            <outputs>
            <data format="tabular" name="tab_file" label="${job_name}"/>

            </outputs>
            <help>
            
**What it Does**

Reverse the columns in a tabular file

            </help>
            <configfiles>
            <configfile name="runMe">
            
# reverse order of columns in a tabular file
import sys
inp = sys.argv[1]
outp = sys.argv[2]
i = open(inp,'r')
o = open(outp,'w')
for row in i:
     rs = row.rstrip().split('\t')
     rs.reverse()
     o.write('\t'.join(rs))
     o.write('\n')
i.close()
o.close()
 

            </configfile>
            </configfiles>
            </tool>
        
        """ 
        newXML="""<tool id="%(toolid)s" name="%(toolname)s" version="%(tool_version)s">
%(tooldesc)s
%(requirements)s
<command interpreter="python">
%(command)s
</command>
<inputs>
%(inputs)s
</inputs>
<outputs>
%(outputs)s
</outputs>
<configfiles>
<configfile name="runMe">
%(script)s
</configfile>
</configfiles>

%(tooltests)s

<help>

%(help)s

</help>
<citations>
    %(citations)s
    <citation type="doi">10.1093/bioinformatics/bts573</citation>
</citations>
</tool>""" # needs a dict with toolname, toolid, interpreter, scriptname, command, inputs as a multi line string ready to write, outputs ditto, help ditto

        newCommand="""
        %(toolname)s.py --script_path "$runMe" --interpreter "%(interpreter)s" 
            --tool_name "%(toolname)s" %(command_inputs)s %(command_outputs)s """
        # may NOT be an input or htmlout - appended later
        tooltestsTabOnly = """
        <tests>
        <test>
        <param name="input1" value="%(test1Input)s" ftype="%(inputFormats)s"/>
        <param name="job_name" value="test1"/>
        <param name="runMe" value="$runMe"/>
        <output name="tab_file" file="%(test1Output)s" ftype="%(outputFormat)s"/>
        </test>
        </tests>
        """
        tooltestsHTMLOnly = """
        <tests>
        <test>
        <param name="input1" value="%(test1Input)s" ftype="%(inputFormats)s"/>
        <param name="job_name" value="test1"/>
        <param name="runMe" value="$runMe"/>
        <output name="html_file" file="%(test1HTML)s" ftype="html" lines_diff="5"/>
        </test>
        </tests>
        """
        tooltestsBoth = """<tests>
        <test>
        <param name="input1" value="%(test1Input)s" ftype="%(inputFormats)s"/>
        <param name="job_name" value="test1"/>
        <param name="runMe" value="$runMe"/>
        <output name="tab_file" file="%(test1Output)s" ftype="%(outputFormat)s" />
        <output name="html_file" file="%(test1HTML)s" ftype="html" lines_diff="10"/>
        </test>
        </tests>
        """
        xdict = {}
        xdict['outputFormat'] = self.outputFormat
        xdict['inputFormats'] = self.inputFormats
        xdict['requirements'] = ''
        if self.opts.make_HTML:
            if self.opts.include_dependencies == "yes":
                xdict['requirements'] = protorequirements
        xdict['tool_version'] = self.opts.tool_version
        xdict['test1Input'] = self.test1Input
        xdict['test1HTML'] = self.test1HTML
        xdict['test1Output'] = self.test1Output   
        if self.opts.make_HTML and self.opts.output_tab <> 'None':
            xdict['tooltests'] = tooltestsBoth % xdict
        elif self.opts.make_HTML:
            xdict['tooltests'] = tooltestsHTMLOnly % xdict
        else:
            xdict['tooltests'] = tooltestsTabOnly % xdict
        xdict['script'] = self.escapedScript 
        # configfile is least painful way to embed script to avoid external dependencies
        # but requires escaping of <, > and $ to avoid Mako parsing
        if self.opts.help_text:
            helptext = open(self.opts.help_text,'r').readlines()
            helptext = [html_escape(x) for x in helptext] # must html escape here too - thanks to Marius van den Beek
            xdict['help'] = ''.join([x for x in helptext])
        else:
            xdict['help'] = 'Please ask the tool author (%s) for help as none was supplied at tool generation\n' % (self.opts.user_email)
        if self.opts.citations:
            citationstext = open(self.opts.citations,'r').read()
            citation_tuples = parse_citations(citationstext)
            citations_xml = ""
            for citation_type, citation_content in citation_tuples:
                citation_xml = """<citation type="%s">%s</citation>""" % (citation_type, html_escape(citation_content))
                citations_xml += citation_xml
            xdict['citations'] = citations_xml
        else:
            xdict['citations'] = ""
        coda = ['**Script**','Pressing execute will run the following code over your input file and generate some outputs in your history::']
        coda.append('\n')
        coda.append(self.indentedScript)
        coda.append('\n**Attribution**\nThis Galaxy tool was created by %s at %s\nusing the Galaxy Tool Factory.\n' % (self.opts.user_email,timenow()))
        coda.append('See %s for details of that project' % (toolFactoryURL))
        coda.append('Please cite: Creating re-usable tools from scripts: The Galaxy Tool Factory. Ross Lazarus; Antony Kaspi; Mark Ziemann; The Galaxy Team. ')
        coda.append('Bioinformatics 2012; doi: 10.1093/bioinformatics/bts573\n')
        xdict['help'] = '%s\n%s' % (xdict['help'],'\n'.join(coda))
        if self.opts.tool_desc:
            xdict['tooldesc'] = '<description>%s</description>' % self.opts.tool_desc
        else:
            xdict['tooldesc'] = ''
        xdict['command_outputs'] = '' 
        xdict['outputs'] = '' 
        if self.opts.input_tab <> 'None':
            xdict['command_inputs'] = '--input_tab "$input1" ' # the space may matter a lot if we append something
            xdict['inputs'] = '<param name="input1"  type="data" format="%s" label="Select a suitable input file from your history"/> \n' % self.inputFormats
        else:
            xdict['command_inputs'] = '' # assume no input - eg a random data generator       
            xdict['inputs'] = ''
        xdict['inputs'] += '<param name="job_name" type="text" label="Supply a name for the outputs to remind you what they contain" value="%s"/> \n' % self.toolname
        xdict['toolname'] = self.toolname
        xdict['toolid'] = self.toolid
        xdict['interpreter'] = self.opts.interpreter
        xdict['scriptname'] = self.sfile
        if self.opts.make_HTML:
            xdict['command_outputs'] += ' --output_dir "$html_file.files_path" --output_html "$html_file" --make_HTML "yes"'
            xdict['outputs'] +=  ' <data format="html" name="html_file" label="${job_name}.html"/>\n'
        else:
            xdict['command_outputs'] += ' --output_dir "./"' 
        if self.opts.output_tab <> 'None':
            xdict['command_outputs'] += ' --output_tab "$tab_file"'
            xdict['outputs'] += ' <data format="%s" name="tab_file" label="${job_name}"/>\n' % self.outputFormat
        xdict['command'] = newCommand % xdict
        xmls = newXML % xdict
        xf = open(self.xmlfile,'w')
        xf.write(xmls)
        xf.write('\n')
        xf.close()
        # ready for the tarball


    def makeTooltar(self):
        """
        a tool is a gz tarball with eg
        /toolname/tool.xml /toolname/tool.py /toolname/test-data/test1_in.foo ...
        """
        retval = self.run()
        if retval:
            print >> sys.stderr,'## Run failed. Cannot build yet. Please fix and retry'
            sys.exit(1)
        tdir = self.toolname
        os.mkdir(tdir)
        self.makeXML()
        if self.opts.make_HTML:
            if self.opts.help_text:
                hlp = open(self.opts.help_text,'r').read()
            else:
                hlp = 'Please ask the tool author for help as none was supplied at tool generation\n'
            if self.opts.include_dependencies:
                tooldepcontent = toolhtmldepskel  % hlp
                depf = open(os.path.join(tdir,'tool_dependencies.xml'),'w')
                depf.write(tooldepcontent)
                depf.write('\n')
                depf.close()
        if self.opts.input_tab <> 'None': # no reproducible test otherwise? TODO: maybe..
            testdir = os.path.join(tdir,'test-data')
            os.mkdir(testdir) # make tests directory
            shutil.copyfile(self.opts.input_tab,os.path.join(testdir,self.test1Input))
            if self.opts.output_tab <> 'None':
                shutil.copyfile(self.opts.output_tab,os.path.join(testdir,self.test1Output))
            if self.opts.make_HTML:
                shutil.copyfile(self.opts.output_html,os.path.join(testdir,self.test1HTML))
            if self.opts.output_dir:
                shutil.copyfile(self.tlog,os.path.join(testdir,'test1_out.log'))
        outpif = '%s.py' % self.toolname # new name
        outpiname = os.path.join(tdir,outpif) # path for the tool tarball
        pyin = os.path.basename(self.pyfile) # our name - we rewrite ourselves (TM)
        notes = ['# %s - a self annotated version of %s generated by running %s\n' % (outpiname,pyin,pyin),]
        notes.append('# to make a new Galaxy tool called %s\n' % self.toolname)
        notes.append('# User %s at %s\n' % (self.opts.user_email,timenow()))
        pi = open(self.pyfile,'r').readlines() # our code becomes new tool wrapper (!) - first Galaxy worm
        notes += pi
        outpi = open(outpiname,'w')
        outpi.write(''.join(notes))
        outpi.write('\n')
        outpi.close()
        stname = os.path.join(tdir,self.sfile)
        if not os.path.exists(stname):
            shutil.copyfile(self.sfile, stname)
        xtname = os.path.join(tdir,self.xmlfile)
        if not os.path.exists(xtname):
            shutil.copyfile(self.xmlfile,xtname)
        tarpath = "%s.gz" % self.toolname
        tar = tarfile.open(tarpath, "w:gz")
        tar.add(tdir,arcname=self.toolname)
        tar.close()
        shutil.copyfile(tarpath,self.opts.new_tool)
        shutil.rmtree(tdir)
        ## TODO: replace with optional direct upload to local toolshed?
        return retval


    def compressPDF(self,inpdf=None,thumbformat='png'):
        """need absolute path to pdf
           note that GS gets confoozled if no $TMP or $TEMP
           so we set it
        """
        assert os.path.isfile(inpdf), "## Input %s supplied to %s compressPDF not found" % (inpdf,self.myName)
        hlog = os.path.join(self.opts.output_dir,"compress_%s.txt" % os.path.basename(inpdf))
        sto = open(hlog,'a')
        our_env = os.environ.copy()
        our_tmp = our_env.get('TMP',None)
        if not our_tmp:
            our_tmp = our_env.get('TEMP',None)
        if not (our_tmp and os.path.exists(our_tmp)):
            newtmp = os.path.join(self.opts.output_dir,'tmp')
            try:
                os.mkdir(newtmp)
            except:
                sto.write('## WARNING - cannot make %s - it may exist or permissions need fixing\n' % newtmp)
            our_env['TEMP'] = newtmp
            if not self.temp_warned:
               sto.write('## WARNING - no $TMP or $TEMP!!! Please fix - using %s temporarily\n' % newtmp)
               self.temp_warned = True          
        outpdf = '%s_compressed' % inpdf
        cl = ["gs", "-sDEVICE=pdfwrite", "-dNOPAUSE", "-dUseCIEColor", "-dBATCH","-dPDFSETTINGS=/printer", "-sOutputFile=%s" % outpdf,inpdf]
        x = subprocess.Popen(cl,stdout=sto,stderr=sto,cwd=self.opts.output_dir,env=our_env)
        retval1 = x.wait()
        sto.close()
        if retval1 == 0:
            os.unlink(inpdf)
            shutil.move(outpdf,inpdf)
            os.unlink(hlog)
        hlog = os.path.join(self.opts.output_dir,"thumbnail_%s.txt" % os.path.basename(inpdf))
        sto = open(hlog,'w')
        outpng = '%s.%s' % (os.path.splitext(inpdf)[0],thumbformat)
        if self.useGM:        
            cl2 = ['gm', 'convert', inpdf, outpng]
        else: # assume imagemagick
            cl2 = ['convert', inpdf + '[0]', outpng]
        x = subprocess.Popen(cl2,stdout=sto,stderr=sto,cwd=self.opts.output_dir,env=our_env)
        retval2 = x.wait()
        sto.close()
        if retval2 == 0:
             os.unlink(hlog)
        retval = retval1 or retval2
        return retval


    def getfSize(self,fpath,outpath):
        """
        format a nice file size string
        """
        size = ''
        fp = os.path.join(outpath,fpath)
        if os.path.isfile(fp):
            size = '0 B'
            n = float(os.path.getsize(fp))
            if n > 2**20:
                size = '%1.1f MB' % (n/2**20)
            elif n > 2**10:
                size = '%1.1f KB' % (n/2**10)
            elif n > 0:
                size = '%d B' % (int(n))
        return size

    def makeHtml(self):
        """ Create an HTML file content to list all the artifacts found in the output_dir
        """

        galhtmlprefix = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"> 
        <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en"> 
        <head> <meta http-equiv="Content-Type" content="text/html; charset=utf-8" /> 
        <meta name="generator" content="Galaxy %s tool output - see http://g2.trac.bx.psu.edu/" /> 
        <title></title> 
        <link rel="stylesheet" href="/static/style/base.css" type="text/css" /> 
        </head> 
        <body> 
        <div class="toolFormBody"> 
        """ 
        galhtmlattr = """<hr/><div class="infomessage">This tool (%s) was generated by the <a href="https://bitbucket.org/fubar/galaxytoolfactory/overview">Galaxy Tool Factory</a></div><br/>""" 
        galhtmlpostfix = """</div></body></html>\n"""

        flist = os.listdir(self.opts.output_dir)
        flist = [x for x in flist if x <> 'Rplots.pdf']
        flist.sort()
        html = []
        html.append(galhtmlprefix % progname)
        html.append('<div class="infomessage">Galaxy Tool "%s" run at %s</div><br/>' % (self.toolname,timenow()))
        fhtml = []
        if len(flist) > 0:
            logfiles = [x for x in flist if x.lower().endswith('.log')] # log file names determine sections
            logfiles.sort()
            logfiles = [x for x in logfiles if os.path.abspath(x) <> os.path.abspath(self.tlog)]
            logfiles.append(os.path.abspath(self.tlog)) # make it the last one
            pdflist = []
            npdf = len([x for x in flist if os.path.splitext(x)[-1].lower() == '.pdf' or os.path.splitext(x)[-1].lower() == '.png'])
            for rownum,fname in enumerate(flist):
                dname,e = os.path.splitext(fname)
                sfsize = self.getfSize(fname,self.opts.output_dir)
                if e.lower() == '.pdf' or e.lower() == '.png' : # compress and make a thumbnail
                    thumb = '%s.%s' % (dname,self.thumbformat)
                    pdff = os.path.join(self.opts.output_dir,fname)
                    retval = self.compressPDF(inpdf=pdff,thumbformat=self.thumbformat)
                    if retval == 0:
                        pdflist.append((fname,thumb))
                    else:
                        pdflist.append((fname,fname))
                if (rownum+1) % 2 == 0:
                    fhtml.append('<tr class="odd_row"><td><a href="%s">%s</a></td><td>%s</td></tr>' % (fname,fname,sfsize))
                else:
                    fhtml.append('<tr><td><a href="%s">%s</a></td><td>%s</td></tr>' % (fname,fname,sfsize))
            for logfname in logfiles: # expect at least tlog - if more
                if os.path.abspath(logfname) == os.path.abspath(self.tlog): # handled later
                    sectionname = 'All tool run'
                    if (len(logfiles) > 1):
                        sectionname = 'Other'
                    ourpdfs = pdflist
                else:
                    realname = os.path.basename(logfname)
                    sectionname = os.path.splitext(realname)[0].split('_')[0] # break in case _ added to log
                    ourpdfs = [x for x in pdflist if os.path.basename(x[0]).split('_')[0] == sectionname]
                    pdflist = [x for x in pdflist if os.path.basename(x[0]).split('_')[0] <> sectionname] # remove
                nacross = 1
                npdf = len(ourpdfs)

                #if npdf > 0:
                #    nacross = math.sqrt(npdf) ## int(round(math.log(npdf,2)))
                #    if int(nacross)**2 != npdf:
                #        nacross += 1
                #    nacross = int(nacross)
                #    width = min(400,int(1200/nacross))
                #    html.append('<div class="toolFormTitle">%s images and outputs</div>' % sectionname)
                #    html.append('(Click on a thumbnail image to download the corresponding original PDF image)<br/>')
                #    ntogo = nacross # counter for table row padding with empty cells
                #    html.append('<div><table class="simple" cellpadding="2" cellspacing="2">\n<tr>')
                #    for i,paths in enumerate(ourpdfs): 
                #        fname,thumb = paths
                #        s= """<td><a href="%s"><img src="%s" title="Click to download a PDF of %s" hspace="5" width="%d" 
                #           alt="Image called %s"/></a></td>\n""" % (fname,thumb,fname,width,fname)
                #        if ((i+1) % nacross == 0):
                #            s += '</tr>\n'
                #            ntogo = 0
                #            if i < (npdf - 1): # more to come
                #               s += '<tr>'
                #               ntogo = nacross
                #        else:
                #            ntogo -= 1
                #        html.append(s)
                #    if html[-1].strip().endswith('</tr>'):
                #        html.append('</table></div>\n')
                #    else:
                #        if ntogo > 0: # pad
                #           html.append('<td>&nbsp;</td>'*ntogo)
                #        html.append('</tr></table></div>\n')
                
                #logt = open(logfname,'r').readlines()
                #logtext = [x for x in logt if x.strip() > '']
                #html.append('<div class="toolFormTitle">%s log output</div>' % sectionname)
                #if len(logtext) > 1:
                #    html.append('\n<pre>\n')
                #    html += logtext
                #    html.append('\n</pre>\n')
                #else:
                #    html.append('%s is empty<br/>' % logfname)
        if len(fhtml) > 0:
           fhtml.insert(0,'<div><table class="colored" cellpadding="3" cellspacing="3"><tr><th>Output File Name (click to view)</th><th>Size</th></tr>\n')
           fhtml.append('</table></div><br/>')
           html.append('<div class="toolFormTitle">All output files available for downloading</div>\n')
           html += fhtml # add all non-pdf files to the end of the display
        else:
            html.append('<div class="warningmessagelarge">### Error - %s returned no files - please confirm that parameters are sane</div>' % self.opts.interpreter)
        html.append(galhtmlpostfix)
        htmlf = file(self.opts.output_html,'w')
        htmlf.write('\n'.join(html))
        htmlf.write('\n')
        htmlf.close()
        self.html = html


    def run(self):
        """
        scripts must be small enough not to fill the pipe!
        """
        if self.treatbashSpecial and self.opts.interpreter in ['bash','sh']:
          retval = self.runBash()
        else:
            if self.opts.output_dir:
                ste = open(self.elog,'w')
                sto = open(self.tlog,'w')
                sto.write('## Toolfactory generated command line = %s\n' % ' '.join(self.cl))
                sto.flush()
                p = subprocess.Popen(self.cl,shell=False,stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.PIPE,cwd=self.opts.output_dir)
                #p = subprocess.Popen(self.cl,shell=False,stdout=sto,stderr=ste,stdin=subprocess.PIPE,cwd=self.opts.output_dir)
            else:
                p = subprocess.Popen(self.cl,shell=False,stdin=subprocess.PIPE)
            p.stdin.write(self.script)
            #p.stdin.close()
            
            stdout_data, stderr_data = p.communicate()
            p.stdin.close()
            #retval = p.wait()
            retval = p.returncode

            if self.opts.output_dir:
                sto.close()
                ste.close()
                err = stderr_data
                #err = open(self.elog,'r').readlines()
	    
            print >> sys.stdout, stdout_data
            
            if retval <> 0 and err: # problem
                print >> sys.stderr,err

            if self.opts.make_HTML:
                self.makeHtml()
        return retval

    def runBash(self):
        """
        cannot use - for bash so use self.sfile
        """
        if self.opts.output_dir:
            s = '## Toolfactory generated command line = %s\n' % ' '.join(self.cl)
            sto = open(self.tlog,'w')
            sto.write(s)
            sto.flush()
            p = subprocess.Popen(self.cl,shell=False,stdout=sto,stderr=sto,cwd=self.opts.output_dir)
        else:
            p = subprocess.Popen(self.cl,shell=False)
        retval = p.wait()
        if self.opts.output_dir:
            sto.close()
        if self.opts.make_HTML:
            self.makeHtml()
        return retval


def main():
    u = """
    This is a Galaxy wrapper. It expects to be called by a special purpose tool.xml as:
    <command interpreter="python">rgBaseScriptWrapper.py --script_path "$scriptPath" --tool_name "foo" --interpreter "Rscript"
    </command>
    """
    op = optparse.OptionParser()
    a = op.add_option
    a('--script_path',default=None)
    a('--tool_name',default=None)
    a('--interpreter',default=None)
    a('--output_dir',default='./')
    a('--output_html',default=None)
    a('--input_tab',default="None")
    a('--notuse_flex',default="TRUE")
    a('--dropout_base',default="4")
    a('--failed_base',default="3")
    a('--input_formats',default="tabular,text")
    a('--output_tab',default="None")
    a('--output_format',default="tabular")
    a('--user_email',default='Unknown')
    a('--bad_user',default=None)
    a('--make_Tool',default=None)
    a('--make_HTML',default=None)
    a('--help_text',default=None)
    a('--citations',default=None)
    a('--tool_desc',default=None)
    a('--new_tool',default=None)
    a('--tool_version',default=None)
    a('--include_dependencies',default=None)    
    a('--count_fpkm',default=None)
    opts, args = op.parse_args()
    assert not opts.bad_user,'UNAUTHORISED: %s is NOT authorized to use this tool until Galaxy admin adds %s to admin_users in universe_wsgi.ini' % (opts.bad_user,opts.bad_user)
    assert opts.tool_name,'## Tool Factory expects a tool name - eg --tool_name=DESeq'
    assert opts.interpreter,'## Tool Factory wrapper expects an interpreter - eg --interpreter=Rscript'
    assert os.path.isfile(opts.script_path),'## Tool Factory wrapper expects a script path - eg --script_path=foo.R'
    if opts.output_dir:
        try:
            os.makedirs(opts.output_dir)
        except:
            pass
    r = ScriptRunner(opts)
    if opts.make_Tool:
        retcode = r.makeTooltar()
    else:
        retcode = r.run()
    os.unlink(r.sfile)
    if retcode:
        sys.exit(retcode) # indicate failure to job runner


if __name__ == "__main__":
    main()



