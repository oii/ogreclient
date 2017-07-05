using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Diagnostics;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Linq;
using System.ServiceProcess;
using System.Text;
using System.Threading.Tasks;
using System.Timers;


namespace OgreClientService
{
    public partial class OgreWrapper : ServiceBase
    {
        private Timer timer;
        private MemoryMappedFile mmf;
        private MemoryMappedViewAccessor accessor;
        private static string python_exe = "C:\\Users\\vagrant\\Desktop\\OGRE\\InnoInstall\\WinPython-64bit-2.7.12.3Zero\\python-2.7.12.amd64\\python.exe";

        public OgreWrapper()
        {
            InitializeComponent();

            timer = new Timer();
            timer.Elapsed += RunOgreClient;
            timer.Interval = 60000;     // 60 secs

            if (!EventLog.SourceExists("OGRE")) {
                EventLog.CreateEventSource("OGRE", "Application");
            }
        }

        private void RunOgreClient(object sender, EventArgs e)
        {
            ProcessStartInfo startInfo = new ProcessStartInfo(python_exe, "ogre sync -q");
            EventLog.WriteEntry("OGRE", "Starting "+startInfo.FileName);
            startInfo.CreateNoWindow = true;
            startInfo.UseShellExecute = false;
            startInfo.RedirectStandardOutput = true;
            startInfo.RedirectStandardError = true;
            startInfo.WindowStyle = ProcessWindowStyle.Hidden;
            //startInfo.WorkingDirectory = textBoxWorkingDirectory.Text;

            using (Process process = Process.Start(startInfo))
            {
                /*p.EnableRaisingEvents = true;
                p.OutputDataReceived += new DataReceivedEventHandler(OnDataReceived);
                p.ErrorDataReceived += new DataReceivedEventHandler(OnDataReceived);
                //p.Exited += new EventHandler(OnProcessExit);
                p.Start();
                p.BeginOutputReadLine();
                p.BeginErrorReadLine();*/

                using (StreamReader reader = process.StandardOutput)
                {
                    string result = reader.ReadToEnd();
                    EventLog.WriteEntry("OGRE", "Result: " + result);

                    byte[] bytes = Encoding.UTF8.GetBytes(result);
                    accessor.WriteArray(0, bytes, 0, bytes.Length);
                }

                EventLog.WriteEntry("OGRE", "End " + process.StandardError.ReadToEnd());
            }

            EventLog.WriteEntry("OGRE", "EGG");
        }

        /*private void OnDataReceived(object sender, System.Diagnostics.DataReceivedEventArgs e)
        {
            // output streamed back from subprocess?
            AddToFile(e.Data);
        }

        private void AddToFile(string contents)
        {
            FileStream fs = new FileStream(@"c:timerserv.txt", FileMode.OpenOrCreate, FileAccess.Write);
            StreamWriter sw = new StreamWriter(fs);
            sw.BaseStream.Seek(0, SeekOrigin.End);
            sw.WriteLine(contents);
            //sw.Flush();
            sw.Close();
        }*/

        protected override void OnStart(string[] args)
        {
            timer.Enabled = true;

            mmf = MemoryMappedFile.CreateFromFile(
                new FileStream(@"C:\temp\Map.mp", FileMode.Create),
                "Ogreclient",
                1024 * 1024,
                MemoryMappedFileAccess.ReadWrite,
                null,
                HandleInheritability.None,
                false
            );
            accessor = mmf.CreateViewAccessor();
        }

        protected override void OnStop()
        {
            timer.Enabled = false;

            accessor.Dispose();
            mmf.Dispose();
        }
    }
}
