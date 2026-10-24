//! memoryd-only SQLite access, bound parameters, consent and explicit confirmation.
use super::*;
use host_core::MemoryRequest;
use std::ffi::{c_char, c_int, c_void, CStr, CString};
unsafe extern "C" {
    fn sqlite3_open(p: *const c_char, db: *mut *mut c_void) -> c_int;
    fn sqlite3_close(db: *mut c_void) -> c_int;
    fn sqlite3_exec(
        db: *mut c_void,
        sql: *const c_char,
        cb: *const c_void,
        arg: *mut c_void,
        err: *mut *mut c_char,
    ) -> c_int;
    fn sqlite3_prepare_v2(
        db: *mut c_void,
        sql: *const c_char,
        n: c_int,
        s: *mut *mut c_void,
        tail: *mut *const c_char,
    ) -> c_int;
    fn sqlite3_bind_text(
        s: *mut c_void,
        i: c_int,
        t: *const c_char,
        n: c_int,
        d: Option<unsafe extern "C" fn(*mut c_void)>,
    ) -> c_int;
    fn sqlite3_step(s: *mut c_void) -> c_int;
    fn sqlite3_column_text(s: *mut c_void, i: c_int) -> *const u8;
    fn sqlite3_finalize(s: *mut c_void) -> c_int;
}
struct Db(*mut c_void);
impl Drop for Db {
    fn drop(&mut self) {
        unsafe {
            sqlite3_close(self.0);
        }
    }
}
struct Stmt(*mut c_void);
impl Drop for Stmt {
    fn drop(&mut self) {
        unsafe {
            sqlite3_finalize(self.0);
        }
    }
}
impl Db {
    fn open(path: &str) -> Result<Self> {
        let mut p = std::ptr::null_mut();
        if unsafe { sqlite3_open(CString::new(path)?.as_ptr(), &mut p) } != 0 {
            if !p.is_null() {
                unsafe {
                    sqlite3_close(p);
                }
            }
            return Err(error("memory open failed"));
        }
        let db = Self(p);
        db.exec("PRAGMA busy_timeout=200; PRAGMA journal_mode=WAL; PRAGMA secure_delete=ON; CREATE TABLE IF NOT EXISTS preferences(id INTEGER PRIMARY KEY CHECK(id=1), consent INTEGER NOT NULL); INSERT OR IGNORE INTO preferences VALUES(1,0); CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY AUTOINCREMENT,text TEXT NOT NULL,source TEXT NOT NULL,created TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%SZ','now'))); CREATE TABLE IF NOT EXISTS goal(id INTEGER PRIMARY KEY CHECK(id=1),text TEXT NOT NULL);")?;
        if !db
            .query("PRAGMA table_info(notes)", &[], 6)?
            .iter()
            .any(|row| row[1] == "updated")
        {
            db.exec("ALTER TABLE notes ADD COLUMN updated TEXT")?;
        }
        Ok(db)
    }
    fn exec(&self, sql: &str) -> Result<()> {
        if unsafe {
            sqlite3_exec(
                self.0,
                CString::new(sql)?.as_ptr(),
                std::ptr::null(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
            )
        } != 0
        {
            return Err(error("memory transaction failed"));
        }
        Ok(())
    }
    fn query(&self, sql: &str, params: &[&str], cols: usize) -> Result<Vec<Vec<String>>> {
        let mut s = std::ptr::null_mut();
        if unsafe {
            sqlite3_prepare_v2(
                self.0,
                CString::new(sql)?.as_ptr(),
                -1,
                &mut s,
                std::ptr::null_mut(),
            )
        } != 0
        {
            return Err(error("memory prepare failed"));
        }
        let s = Stmt(s);
        let strings: Vec<CString> = params
            .iter()
            .map(|t| CString::new(*t))
            .collect::<std::result::Result<_, _>>()?;
        for (i, t) in strings.iter().enumerate() {
            if unsafe { sqlite3_bind_text(s.0, i as i32 + 1, t.as_ptr(), -1, None) } != 0 {
                return Err(error("memory bind failed"));
            }
        }
        let mut rows = Vec::new();
        loop {
            match unsafe { sqlite3_step(s.0) } {
                101 => break,
                100 => {
                    if rows.len() >= 1000 {
                        return Err(error("memory response limit"));
                    }
                    let row = (0..cols)
                        .map(|i| {
                            let p = unsafe { sqlite3_column_text(s.0, i as i32) };
                            if p.is_null() {
                                String::new()
                            } else {
                                unsafe { CStr::from_ptr(p.cast()) }
                                    .to_string_lossy()
                                    .into_owned()
                            }
                        })
                        .collect();
                    rows.push(row);
                }
                _ => return Err(error("memory step failed")),
            }
        }
        Ok(rows)
    }
}
pub fn execute(path: &str, r: MemoryRequest) -> Result<Value> {
    let db = Db::open(path)?;
    let consent = db.query("SELECT consent FROM preferences WHERE id=1", &[], 1)?[0][0] == "1";
    match r {
        MemoryRequest::Consent { enabled } => {
            db.exec(if enabled {
                "UPDATE preferences SET consent=1 WHERE id=1"
            } else {
                "UPDATE preferences SET consent=0 WHERE id=1"
            })?;
            Ok(json!({"consent":enabled,"existing_notes_retained":true}))
        }
        MemoryRequest::Save {
            text,
            confirmed,
            source,
        } => {
            if !consent || !confirmed {
                return Err(error("memory requires opt-in and user confirmation"));
            }
            if text.trim().is_empty() || text.len() > 2048 || source.len() > 128 {
                return Err(error("memory size invalid"));
            }
            let count = db.query("SELECT count(*) FROM notes", &[], 1)?[0][0].parse::<u32>()?;
            if count >= 500 {
                return Err(error("memory full; review/delete old notes"));
            }
            db.query(
                "INSERT INTO notes(text,source) VALUES(?,?)",
                &[&text, &source],
                0,
            )?;
            Ok(
                json!({"saved":true,"id":db.query("SELECT last_insert_rowid()",&[],1)?[0][0].parse::<u64>()?}),
            )
        }
        MemoryRequest::Update {
            id,
            text,
            confirmed,
            source,
        } => {
            if !consent || !confirmed {
                return Err(error("memory requires opt-in and user confirmation"));
            }
            if text.trim().is_empty() || text.len() > 2048 || source.len() > 128 {
                return Err(error("memory size invalid"));
            }
            db.query("UPDATE notes SET text=?,source=?,updated=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", &[&text, &source, &id.to_string()], 0)?;
            if db.query("SELECT changes()", &[], 1)?[0][0] != "1" {
                return Err(error("memory note not found"));
            }
            db.exec("PRAGMA wal_checkpoint(TRUNCATE)")?;
            Ok(json!({"updated":true,"id":id}))
        }
        MemoryRequest::Search { query } => {
            if !consent {
                return Ok(json!({"consent":false,"notes":[]}));
            }
            if query.len() > 2048 {
                return Err(error("query too long"));
            }
            // instr treats SQL wildcard and quote characters as ordinary text.
            let rows=db.query("SELECT id,text,source,created,COALESCE(updated,created) FROM notes WHERE instr(lower(text),lower(?))>0 ORDER BY id DESC LIMIT 8",&[&query],5)?;
            Ok(
                json!({"consent":true,"notes":rows.into_iter().map(|r|json!({"id":r[0],"text":r[1],"source":r[2],"created":r[3],"confirmed_at":r[4]})).collect::<Vec<_>>()}),
            )
        }
        MemoryRequest::List { before } | MemoryRequest::Export { before } => {
            let cursor = before.to_string();
            let rows=db.query("SELECT id,text,source,created,COALESCE(updated,created) FROM notes WHERE id < ? OR ?='0' ORDER BY id DESC LIMIT 20",&[&cursor,&cursor],5)?;
            let next = if rows.len() == 20 {
                rows.last().map(|r| r[0].clone())
            } else {
                None
            };
            let goal = db
                .query("SELECT text FROM goal WHERE id=1", &[], 1)?
                .first()
                .map(|r| r[0].clone())
                .unwrap_or_default();
            Ok(
                json!({"consent":consent,"goal":goal,"next_before":next,"notes":rows.into_iter().map(|r|json!({"id":r[0],"text":r[1],"source":r[2],"created":r[3],"confirmed_at":r[4]})).collect::<Vec<_>>()}),
            )
        }
        MemoryRequest::Delete { id } => {
            db.query("DELETE FROM notes WHERE id=?", &[&id.to_string()], 0)?;
            db.exec("PRAGMA wal_checkpoint(TRUNCATE)")?;
            Ok(json!({"deleted":id}))
        }
        MemoryRequest::DeleteAll => {
            db.exec("BEGIN IMMEDIATE; DELETE FROM notes; DELETE FROM goal; UPDATE preferences SET consent=0; COMMIT; PRAGMA wal_checkpoint(TRUNCATE); VACUUM;")?;
            Ok(json!({"deleted_all":true,"consent":false}))
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn update_requires_confirmation_and_preserves_id_after_reopen() {
        let path =
            std::env::temp_dir().join(format!("learning-update-{}.sqlite", std::process::id()));
        let p = path.to_str().unwrap();
        execute(p, MemoryRequest::Consent { enabled: true }).unwrap();
        let id = execute(
            p,
            MemoryRequest::Save {
                text: "독서 5쪽".into(),
                confirmed: true,
                source: "user".into(),
            },
        )
        .unwrap()["id"]
            .as_u64()
            .unwrap();
        let update = |id, confirmed| MemoryRequest::Update {
            id,
            text: "독서 3쪽'; DROP TABLE notes; --".into(),
            confirmed,
            source: "user correction".into(),
        };
        assert!(execute(p, update(id, false)).is_err());
        assert!(execute(p, update(id + 1, true)).is_err());
        execute(p, update(id, true)).unwrap();
        let notes = execute(p, MemoryRequest::List { before: 0 }).unwrap();
        assert_eq!(notes["notes"][0]["id"], id.to_string());
        assert_eq!(notes["notes"][0]["text"], "독서 3쪽'; DROP TABLE notes; --");
        assert!(notes["notes"][0]["confirmed_at"]
            .as_str()
            .unwrap()
            .ends_with('Z'));
        execute(p, MemoryRequest::Consent { enabled: false }).unwrap();
        assert!(execute(p, update(id, true)).is_err());
        execute(p, MemoryRequest::DeleteAll).unwrap();
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn consent_confirm_search_delete_and_reopen() {
        let path = std::env::temp_dir().join(format!("learning-{}.sqlite", std::process::id()));
        let p = path.to_str().unwrap();
        let save = || MemoryRequest::Save {
            text: "독서'; DROP TABLE notes; --".into(),
            confirmed: true,
            source: "user".into(),
        };
        assert!(execute(p, save()).is_err());
        execute(p, MemoryRequest::Consent { enabled: true }).unwrap();
        execute(p, save()).unwrap();
        let v = execute(
            p,
            MemoryRequest::Search {
                query: "독서".into(),
            },
        )
        .unwrap();
        assert_eq!(v["notes"].as_array().unwrap().len(), 1);
        execute(p, MemoryRequest::DeleteAll).unwrap();
        assert_eq!(
            execute(p, MemoryRequest::List { before: 0 }).unwrap()["notes"],
            json!([])
        );
        std::fs::remove_file(path).unwrap();
    }
}
