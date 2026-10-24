use std::{env, path::PathBuf, process::Command};
fn main() {
    println!("cargo:rerun-if-changed=../../native/media.c");
    println!("cargo:rerun-if-changed=../../native/vision.cu");
    println!("cargo:rerun-if-changed=../../native/detector.cpp");
    println!("cargo:rustc-check-cfg=cfg(has_cuda)");
    println!("cargo:rustc-check-cfg=cfg(has_detector)");
    let out = PathBuf::from(env::var("OUT_DIR").unwrap());
    let flags = Command::new("pkg-config")
        .args(["--cflags", "gstreamer-app-1.0", "sqlite3"])
        .output()
        .expect("pkg-config required");
    assert!(
        flags.status.success(),
        "GStreamer app development headers required"
    );
    let mut cc = Command::new("cc");
    cc.args([
        "-O2",
        "-fPIC",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-c",
        "../../native/media.c",
        "-o",
    ])
    .arg(out.join("media.o"));
    cc.args(String::from_utf8(flags.stdout).unwrap().split_whitespace());
    assert!(cc.status().unwrap().success());
    let mut objects = vec![out.join("media.o")];
    let detector = std::path::Path::new("/usr/include/aarch64-linux-gnu/NvInfer.h").exists();
    if detector {
        let flags = Command::new("pkg-config")
            .args(["--cflags", "opencv4"])
            .output()
            .unwrap();
        assert!(flags.status.success());
        assert!(Command::new("c++")
            .args([
                "-std=c++14",
                "-O2",
                "-fPIC",
                "-I/usr/local/cuda/include",
                "-I/usr/include/aarch64-linux-gnu",
                "-c",
                "../../native/detector.cpp",
                "-o"
            ])
            .arg(out.join("detector.o"))
            .args(String::from_utf8(flags.stdout).unwrap().split_whitespace())
            .status()
            .unwrap()
            .success());
        objects.push(out.join("detector.o"));
        println!("cargo:rustc-cfg=has_detector");
    }
    let nvcc = "/usr/local/cuda/bin/nvcc";
    if std::path::Path::new(nvcc).exists() {
        assert!(Command::new(nvcc)
            .args([
                "-O2",
                "-arch=sm_53",
                "-Xcompiler",
                "-fPIC",
                "-c",
                "../../native/vision.cu",
                "-o"
            ])
            .arg(out.join("vision.o"))
            .status()
            .unwrap()
            .success());
        objects.push(out.join("vision.o"));
        println!("cargo:rustc-cfg=has_cuda");
        println!("cargo:rustc-link-search=native=/usr/local/cuda/lib64");
    }
    assert!(Command::new("ar")
        .arg("crs")
        .arg(out.join("libnano_native.a"))
        .args(objects)
        .status()
        .unwrap()
        .success());
    println!("cargo:rustc-link-search=native={}", out.display());
    println!("cargo:rustc-link-lib=static=nano_native");
    if detector {
        for lib in [
            "nvinfer",
            "opencv_core",
            "opencv_imgproc",
            "opencv_dnn",
            "opencv_objdetect",
        ] {
            println!("cargo:rustc-link-lib={lib}");
        }
    }
    if std::path::Path::new(nvcc).exists() {
        println!("cargo:rustc-link-lib=cudart");
        println!("cargo:rustc-link-lib=stdc++");
    }
    let libs = Command::new("pkg-config")
        .args(["--libs", "gstreamer-app-1.0", "sqlite3"])
        .output()
        .unwrap();
    for flag in String::from_utf8(libs.stdout).unwrap().split_whitespace() {
        if let Some(lib) = flag.strip_prefix("-l") {
            println!("cargo:rustc-link-lib={lib}");
        }
        if let Some(path) = flag.strip_prefix("-L") {
            println!("cargo:rustc-link-search=native={path}");
        }
    }
}
