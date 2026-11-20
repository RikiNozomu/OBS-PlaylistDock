// SPDX-License-Identifier: GPL-2.0-or-later
#include "PlaylistDock.hpp"
#include <obs-module.h>
#include <obs-frontend-api.h>
#include <QPointer>

// Built against OBS 32.x headers; the libobs/frontend ABI used here is unchanged in OBS 33.
#if LIBOBS_API_MAJOR_VER < 32 || LIBOBS_API_MAJOR_VER > 33
#error Build OBS-PlaylistDock against OBS 32.x or 33.x headers.
#endif

namespace {
constexpr uint32_t MinObsMajor = 32;
constexpr uint32_t MaxObsMajor = 33;
}

OBS_DECLARE_MODULE()
OBS_MODULE_USE_DEFAULT_LOCALE("obs-playlistdock", "en-US")
MODULE_EXPORT const char *obs_module_name() { return obs_module_text("DockName"); }
MODULE_EXPORT const char *obs_module_description() { return obs_module_text("PluginDescription"); }
MODULE_EXPORT const char *obs_module_author() { return "haliluya.net"; }

namespace {
constexpr const char *DockId = "OBS-PlaylistDock";
QPointer<PlaylistDock> dock;
bool exiting = false;

void frontendEvent(obs_frontend_event event, void *)
{
    if (!dock)
        return;
    switch (event) {
    case OBS_FRONTEND_EVENT_FINISHED_LOADING:
    case OBS_FRONTEND_EVENT_SCENE_COLLECTION_CHANGED:
        dock->resume();
        break;
    case OBS_FRONTEND_EVENT_SCENE_COLLECTION_CHANGING:
    case OBS_FRONTEND_EVENT_SCENE_COLLECTION_CLEANUP:
        dock->suspend();
        break;
    case OBS_FRONTEND_EVENT_EXIT:
        exiting = true;
        dock->shutdown();
        break;
    default:
        break;
    }
}
}

bool obs_module_load()
{
    const uint32_t obsMajor = obs_get_version() >> 24;
    if (obsMajor < MinObsMajor || obsMajor > MaxObsMajor) {
        blog(LOG_ERROR, "[OBS-PlaylistDock] This build requires OBS 32.x or 33.x; running %s.", obs_get_version_string());
        return false;
    }
    if (!QString::fromLatin1(qVersion()).startsWith(QStringLiteral("%1.%2.").arg(QT_VERSION_MAJOR).arg(QT_VERSION_MINOR))) {
        blog(LOG_ERROR, "[OBS-PlaylistDock] This build requires Qt %d.%d.x; runtime is %s.", QT_VERSION_MAJOR, QT_VERSION_MINOR, qVersion());
        return false;
    }
    char *configPath = obs_module_config_path("settings.json");
    const QString settingsFile = QString::fromUtf8(configPath ? configPath : "");
    bfree(configPath);
    auto *widget = new PlaylistDock(settingsFile);
    if (!obs_frontend_add_dock_by_id(DockId, obs_module_text("DockName"), widget)) {
        delete widget;
        return false;
    }
    dock = widget;
    QObject::connect(widget, &PlaylistDock::configurationChanged, widget, [] { obs_frontend_save(); });
    exiting = false;
    obs_frontend_add_event_callback(frontendEvent, nullptr);
    blog(LOG_INFO, "[OBS-PlaylistDock] %s loaded; Qt %s; dock registered.", PLAYLISTDOCK_VERSION, qVersion());
    return true;
}

void obs_module_unload()
{
    obs_frontend_remove_event_callback(frontendEvent, nullptr);
    if (!dock)
        return;
    dock->shutdown();
    if (!exiting)
        obs_frontend_remove_dock(DockId);
    // Destroy the widget before unloading its class code.
    if (dock)
        delete dock.data();
    dock.clear();
}
