#if UNITY_EDITOR
using UnityEngine;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.XR.Management;
using UnityEngine.XR.Management;

namespace PicoMultiModalCapture
{
    // ======================================================================
    // Build preprocessor: runs BEFORE BuildHelperUtils (-100) to force XR
    // loader initialization. This prevents ArgumentNullException in
    // BuildHelperUtils.HasLoader -> settings.Manager.loaders.Any().
    //
    // Root cause: XRManagerSettings.loaders (obsolete singular property)
    // returns null when active loaders haven't been lazily initialized.
    // BuildHelperUtils fails to null-check before calling .Any().
    //
    // This preprocessor accesses activeLoaders early in the build pipeline,
    // forcing lazy initialization so the list is non-null when
    // PICOModifyAndroidManifest -> IsExtensionEnabled -> HasLoader runs.
    // ======================================================================
    public class PicoBuildPreprocessor : IPreprocessBuildWithReport
    {
        public int callbackOrder => -200;

        public void OnPreprocessBuild(BuildReport report)
        {
            if (report.summary.platform != BuildTarget.Android) return;

            Debug.Log("[PicoBuildFix] Preprocessor: forcing XR loader init for Android...");

            try
            {
                var settingsForAndroid = XRGeneralSettingsPerBuildTarget
                    .XRGeneralSettingsForBuildTarget(BuildTargetGroup.Android);

                if (settingsForAndroid == null)
                {
                    Debug.LogError("[PicoBuildFix] CRITICAL: XRGeneralSettings is null for Android!");
                    return;
                }

                var manager = settingsForAndroid.Manager;
                if (manager == null)
                {
                    Debug.LogError("[PicoBuildFix] CRITICAL: XRManagerSettings is null!");
                    return;
                }

                // Forcing access to activeLoaders triggers lazy loader creation
                // from the serialized m_Loaders MonoScript list.
                var loaders = manager.activeLoaders;
                int count = loaders?.Count ?? 0;
                Debug.Log($"[PicoBuildFix] activeLoaders count: {count}");

                if (count == 0)
                {
                    Debug.LogWarning("[PicoBuildFix] No active loaders. Running InitializeLoaderSync...");
                    manager.InitializeLoaderSync();
                    loaders = manager.activeLoaders;
                    Debug.Log($"[PicoBuildFix] After InitializeLoaderSync: {loaders?.Count ?? 0} loaders");

                    if ((loaders?.Count ?? 0) == 0)
                    {
                        Debug.LogError("[PicoBuildFix] STILL no loaders after InitializeLoaderSync! "
                            + "Check Project Settings > XR Plug-in Management > Android tab.");
                    }
                }

                // Touch the obsolete singular loader property to ensure the cached
                // internal state is populated for BuildHelperUtils.HasLoader()
#pragma warning disable CS0618
                var single = manager.loaders;
                Debug.Log($"[PicoBuildFix] Singular loader: {(single != null ? single.GetType().Name : "NULL")}");
#pragma warning restore CS0618
            }
            catch (System.Exception ex)
            {
                Debug.LogError($"[PicoBuildFix] Error: {ex.Message}\n{ex.StackTrace}");
            }
        }
    }
}
#endif
