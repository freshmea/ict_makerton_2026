#include <stdio.h>
#include <alsa/asoundlib.h>
#include <gst/gst.h>
#include <libudev.h>
#include <openssl/ssl.h>
#include <sqlite3.h>

int main(int argc, char **argv) {
    gst_init(&argc, &argv);
    struct udev *udev = udev_new();
    SSL_CTX *tls = SSL_CTX_new(TLS_method());
    sqlite3 *db = NULL;
    if (!udev || !tls || sqlite3_open(":memory:", &db) != SQLITE_OK) return 1;
    const char *plugins[] = {"nvarguscamerasrc", "nvvidconv", "nvv4l2h264enc",
                             "webrtcdsp", "webrtcechoprobe", "alsasrc", "alsasink"};
    for (size_t i = 0; i < sizeof(plugins) / sizeof(plugins[0]); ++i) {
        GstElementFactory *factory = gst_element_factory_find(plugins[i]);
        if (!factory) { fprintf(stderr, "Missing element: %s\n", plugins[i]); return 2; }
        printf("Element registered: %s\n", plugins[i]);
        gst_object_unref(factory);
    }
    printf("Native link/load OK: GStreamer=%s ALSA=%s SQLite=%s OpenSSL=%s\n",
           gst_version_string(), snd_asoundlib_version(), sqlite3_libversion(), OpenSSL_version(OPENSSL_VERSION));
    sqlite3_close(db);
    SSL_CTX_free(tls);
    udev_unref(udev);
    gst_deinit();
    return 0;
}
