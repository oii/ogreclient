using System;
using System.Windows.Forms;
using System.Reflection;
using System.Drawing;

namespace OgreClientTray
{
    public class AppContext : ApplicationContext
    {
        // Icon graphic from http://prothemedesign.com/circular-icons/
        private static readonly string IconFileName = "route.ico";
        private static readonly string DefaultTooltip = "View OGRE Logs";
        //private readonly HostManager hostManager;

        /// <summary>
		/// This class should be created and passed into Application.Run( ... )
		/// </summary>
		public AppContext()
        {
            InitializeContext();
            //hostManager = new HostManager(notifyIcon);
            //hostManager.BuildServerAssociations();
            //if (!hostManager.IsDecorated) { ShowIntroForm(); }
        }

        /*private void ContextMenuStrip_Opening(object sender, System.ComponentModel.CancelEventArgs e)
        {
            e.Cancel = false;
            //hostManager.BuildServerAssociations();
            //hostManager.BuildContextMenu(notifyIcon.ContextMenuStrip);
            notifyIcon.ContextMenuStrip.Items.Add(new ToolStripSeparator());
            notifyIcon.ContextMenuStrip.Items.Add(new ToolStripMenuItem("View OGRE Logs"));//, showDetailsItem_Click));
            //notifyIcon.ContextMenuStrip.Items.Add(hostManager.ToolStripMenuItemWithHandler("&Help/About", showHelpItem_Click));
            notifyIcon.ContextMenuStrip.Items.Add(new ToolStripSeparator());
            notifyIcon.ContextMenuStrip.Items.Add(hostManager.ToolStripMenuItemWithHandler("&Exit", exitItem_Click));
        }*/

        private Form1 detailsForm;

        // From http://stackoverflow.com/questions/2208690/invoke-notifyicons-context-menu
        private void notifyIcon_MouseUp(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                MethodInfo mi = typeof(NotifyIcon).GetMethod("ShowContextMenu", BindingFlags.Instance | BindingFlags.NonPublic);
                mi.Invoke(notifyIcon, null);
            }
        }

        // attach to context menu items
        private void showDetailsItem_Click(object sender, EventArgs e) {
            if (detailsForm == null) {
                detailsForm = new Form1 { /*HostManager = hostManager*/ };
                detailsForm.Closed += detailsForm_Closed; // avoid reshowing a disposed form
                detailsForm.Show();
            } else {
                detailsForm.Activate();
            }
        }

        // null out the forms so we know to create a new one.
        private void detailsForm_Closed(object sender, EventArgs e) { detailsForm = null; }

        private System.ComponentModel.IContainer components;
        private NotifyIcon notifyIcon;

        private void InitializeContext()
        {
            components = new System.ComponentModel.Container();
            notifyIcon = new NotifyIcon(components)
            {
                ContextMenuStrip = new ContextMenuStrip(),
                Icon = new Icon(IconFileName),
                Text = DefaultTooltip,
                Visible = true
            };
            ToolStripMenuItem showLogsMenuItem = new ToolStripMenuItem("View OGRE &Logs");
            showLogsMenuItem.Click += showDetailsItem_Click;
            notifyIcon.ContextMenuStrip.Items.Add(showLogsMenuItem);

            ToolStripMenuItem exitMenuItem = new ToolStripMenuItem("&Exit");
            exitMenuItem.Click += exitItem_Click;
            notifyIcon.ContextMenuStrip.Items.Add(exitMenuItem);

            notifyIcon.MouseUp += notifyIcon_MouseUp;
            //notifyIcon.ContextMenuStrip.Opening += ContextMenuStrip_Opening;
            //notifyIcon.DoubleClick += notifyIcon_DoubleClick;
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && components != null) { components.Dispose(); }
        }

        /// <summary>
        /// When the exit menu item is clicked, make a call to terminate the ApplicationContext.
        /// </summary>
        /// <param name="sender"></param>
        /// <param name="e"></param>
        private void exitItem_Click(object sender, EventArgs e)
        {
            ExitThread();
        }

        /// <summary>
        /// If we are presently showing a form, clean it up.
        /// </summary>
        protected override void ExitThreadCore()
        {
            // before we exit, let forms clean themselves up.
            //if (introForm != null) { introForm.Close(); }
            if (detailsForm != null) { detailsForm.Close(); }

            notifyIcon.Visible = false; // should remove lingering tray icon
            base.ExitThreadCore();
        }

    }
}
