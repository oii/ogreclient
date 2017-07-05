namespace OgreClientService
{
    partial class ProjectInstaller
    {
        /// <summary>
        /// Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary> 
        /// Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Component Designer generated code

        /// <summary>
        /// Required method for Designer support - do not modify
        /// the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            this.OgreProcessInstaller = new System.ServiceProcess.ServiceProcessInstaller();
            this.OgreInstaller = new System.ServiceProcess.ServiceInstaller();
            // 
            // OgreProcessInstaller
            // 
            this.OgreProcessInstaller.Account = System.ServiceProcess.ServiceAccount.LocalSystem;
            this.OgreProcessInstaller.Password = null;
            this.OgreProcessInstaller.Username = null;
            // 
            // OgreInstaller
            // 
            this.OgreInstaller.Description = "OGRE client service";
            this.OgreInstaller.DisplayName = "OGRE";
            this.OgreInstaller.ServiceName = "OGRE";
            this.OgreInstaller.StartType = System.ServiceProcess.ServiceStartMode.Automatic;
            // 
            // ProjectInstaller
            // 
            this.Installers.AddRange(new System.Configuration.Install.Installer[] {
            this.OgreProcessInstaller,
            this.OgreInstaller});

        }

        #endregion

        private System.ServiceProcess.ServiceProcessInstaller OgreProcessInstaller;
        private System.ServiceProcess.ServiceInstaller OgreInstaller;
    }
}