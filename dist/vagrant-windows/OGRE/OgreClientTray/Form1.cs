using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace OgreClientTray
{
    public partial class Form1 : Form
    {
        private MemoryMappedFile mmf;
        private MemoryMappedViewAccessor accessor;

        public Form1()
        {
            InitializeComponent();
        }

        public void Read()
        {
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

        private void Form1_OnActivated(object sender, EventArgs e)
        {
            // read from the memory-mapped file when form is activated
            byte[] readBuffer = new byte[1024 * 1024];
            accessor.ReadArray(54 + 2, readBuffer, 0, readBuffer.Length);
            txtConsole.Text += Encoding.UTF8.GetString(readBuffer);
        }
    }
}
