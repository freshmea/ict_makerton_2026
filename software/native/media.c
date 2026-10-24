#include <gst/gst.h>
#include <gst/app/gstappsink.h>
#include <gst/app/gstappsrc.h>
#include <sqlite3.h>
#include <string.h>
#include <stdlib.h>
typedef struct { GstElement *pipe, *sink, *src; GstClockTime next_pts; GstPad *raw_pad; gulong raw_probe; gint source_frames; } Media;
void nano_media_close(void *ptr);
static GstPadProbeReturn count_source(GstPad *pad,GstPadProbeInfo *info,gpointer ptr){(void)pad;(void)info;Media *m=ptr;g_atomic_int_inc(&m->source_frames);return GST_PAD_PROBE_OK;}
void *nano_media_open(const char *pipeline) {
    gst_init(NULL, NULL); GError *error = NULL;
    GstElement *p = gst_parse_launch(pipeline, &error);
    if (error || !p) { if(error) { g_printerr("media parse: %s\n",error->message); g_error_free(error); } if(p) gst_object_unref(p); return NULL; }
    Media *m = calloc(1,sizeof(Media)); m->pipe=p;m->next_pts=GST_CLOCK_TIME_NONE;
    m->sink=gst_bin_get_by_name(GST_BIN(p),"capture"); m->src=gst_bin_get_by_name(GST_BIN(p),"play");
    GstElement *raw=gst_bin_get_by_name(GST_BIN(p),"raw_source");if(raw){m->raw_pad=gst_element_get_static_pad(raw,"src");if(m->raw_pad)m->raw_probe=gst_pad_add_probe(m->raw_pad,GST_PAD_PROBE_TYPE_BUFFER,count_source,m,NULL);gst_object_unref(raw);}
    if(m->src){GstCaps *caps=gst_caps_from_string("audio/x-raw,format=S16LE,layout=interleaved,rate=48000,channels=1");gst_app_src_set_caps(GST_APP_SRC(m->src),caps);gst_caps_unref(caps);gst_app_src_set_latency(GST_APP_SRC(m->src),0,100*GST_MSECOND);}
    if (gst_element_set_state(p,GST_STATE_PLAYING)==GST_STATE_CHANGE_FAILURE) { nano_media_close(m);return NULL; }
    return m;
}
int nano_media_read(void *ptr,unsigned char *dest,int maxlen) {
    Media *m=ptr; GstBus *bus=gst_element_get_bus(m->pipe);
    GstMessage *msg=gst_bus_pop_filtered(bus,GST_MESSAGE_ERROR|GST_MESSAGE_EOS); gst_object_unref(bus);
    if(msg) { if(GST_MESSAGE_TYPE(msg)==GST_MESSAGE_ERROR) { GError *e=NULL;gchar *debug=NULL;gst_message_parse_error(msg,&e,&debug);g_printerr("media error: %s\n",e->message);g_error_free(e);g_free(debug); } gst_message_unref(msg);return -1; }
    GstSample *s=gst_app_sink_try_pull_sample(GST_APP_SINK(m->sink),100*GST_MSECOND); if(!s)return 0;
    GstMapInfo map; GstBuffer *b=gst_sample_get_buffer(s);int count=-1;
    if(gst_buffer_map(b,&map,GST_MAP_READ)){if(map.size<=(gsize)maxlen){memcpy(dest,map.data,map.size);count=(int)map.size;}gst_buffer_unmap(b,&map);}
    gst_sample_unref(s);return count;
}
unsigned int nano_media_source_frames(void *ptr){Media *m=ptr;return (unsigned int)g_atomic_int_get(&m->source_frames);}
int nano_media_push(void *ptr,const unsigned char *pcm,int size) {
    Media *m=ptr;if(!m->src)return -1;
    if(gst_app_src_get_current_level_bytes(GST_APP_SRC(m->src))+(guint64)size>9600)return 2;
    GstBuffer *b=gst_buffer_new_allocate(NULL,size,NULL);gst_buffer_fill(b,0,pcm,size);
    GST_BUFFER_DURATION(b)=gst_util_uint64_scale((guint64)size/2,GST_SECOND,48000);
    GstClock *clock=gst_element_get_clock(m->pipe);GstClockTime now=0;
    if(clock){GstClockTime current=gst_clock_get_time(clock),base=gst_element_get_base_time(m->pipe);if(current>=base)now=current-base;gst_object_unref(clock);}
    if(m->next_pts==GST_CLOCK_TIME_NONE||m->next_pts+50*GST_MSECOND<now)m->next_pts=now;
    GST_BUFFER_PTS(b)=m->next_pts;GST_BUFFER_DTS(b)=m->next_pts;m->next_pts+=GST_BUFFER_DURATION(b);
    return gst_app_src_push_buffer(GST_APP_SRC(m->src),b)==GST_FLOW_OK?0:-1;
}
int nano_media_reset(void *ptr) {
    Media *m=ptr;
    m->next_pts=GST_CLOCK_TIME_NONE;
    // Stop all device-side playback buffers. Capture/AEC restart together.
    if(gst_element_set_state(m->pipe,GST_STATE_NULL)==GST_STATE_CHANGE_FAILURE)return -1;
    gst_element_get_state(m->pipe,NULL,NULL,2*GST_SECOND);
    return gst_element_set_state(m->pipe,GST_STATE_PLAYING)==GST_STATE_CHANGE_FAILURE?-1:0;
}
int nano_media_snapshot(void *ptr,unsigned char *dest,int cap) {
    Media *m=ptr;GstElement *gate=gst_bin_get_by_name(GST_BIN(m->pipe),"problem_gate"),*sink=gst_bin_get_by_name(GST_BIN(m->pipe),"problem");
    if(!gate||!sink){if(gate)gst_object_unref(gate);if(sink)gst_object_unref(sink);return -1;}
    GstSample *old;while((old=gst_app_sink_try_pull_sample(GST_APP_SINK(sink),0)))gst_sample_unref(old);
    g_object_set(gate,"drop",FALSE,NULL);GstSample *s=gst_app_sink_try_pull_sample(GST_APP_SINK(sink),500*GST_MSECOND);g_object_set(gate,"drop",TRUE,NULL);
    int n=-1;if(s){GstMapInfo map;GstBuffer *b=gst_sample_get_buffer(s);if(gst_buffer_map(b,&map,GST_MAP_READ)){if(map.size<=(gsize)cap){memcpy(dest,map.data,map.size);n=(int)map.size;}gst_buffer_unmap(b,&map);}gst_sample_unref(s);}
    gst_object_unref(gate);gst_object_unref(sink);return n;
}
void nano_media_close(void *ptr) { Media *m=ptr;if(!m)return;gst_element_set_state(m->pipe,GST_STATE_NULL);gst_element_get_state(m->pipe,NULL,NULL,2*GST_SECOND);if(m->raw_pad){gst_pad_remove_probe(m->raw_pad,m->raw_probe);gst_object_unref(m->raw_pad);}if(m->sink)gst_object_unref(m->sink);if(m->src)gst_object_unref(m->src);gst_object_unref(m->pipe);free(m); }
// Single memoryd owner; parameter binding prevents SQL injection.
int nano_goal(const char *path,int operation,const char *text,char *out,int cap) {
    sqlite3 *db=NULL;sqlite3_stmt *s=NULL;int rc=-1;
    if(sqlite3_open(path,&db)!=SQLITE_OK)goto done;
    sqlite3_busy_timeout(db,200);
    if(sqlite3_exec(db,"PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS goal(id INTEGER PRIMARY KEY CHECK(id=1), text TEXT NOT NULL);",NULL,NULL,NULL)!=SQLITE_OK)goto done;
    const char *sql=operation==1?"INSERT INTO goal VALUES(1,?) ON CONFLICT(id) DO UPDATE SET text=excluded.text":operation==2?"DELETE FROM goal":"SELECT text FROM goal WHERE id=1";
    if(sqlite3_prepare_v2(db,sql,-1,&s,NULL)!=SQLITE_OK)goto done;
    if(operation==1)sqlite3_bind_text(s,1,text,-1,SQLITE_TRANSIENT);
    int step=sqlite3_step(s);if(step!=SQLITE_DONE&&step!=SQLITE_ROW)goto done;
    if(step==SQLITE_ROW){const unsigned char *v=sqlite3_column_text(s,0);if((int)strlen((const char*)v)>=cap)goto done;strcpy(out,(const char*)v);}else if(cap>0)out[0]=0;
    rc=0;
done: if(s)sqlite3_finalize(s);if(db)sqlite3_close(db);return rc;
}
