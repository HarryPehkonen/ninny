// FROZEN -- the command line the tool presents. Implement src/lib.rs, not this.
//
//   intset normalize <set>      canonical set on stdout        exit 0
//   intset has <set> <n>        yes or no                      exit 0
//   intset add <set> <n>        canonical set on stdout        exit 0
//   anything else               usage on stderr                exit 2
//   input the contract rejects  a message on stderr            exit 1
use std::process::ExitCode;

use intset::{add, contains, normalize};

fn usage() -> ExitCode {
    eprintln!(
        "usage: intset normalize <set>\n       intset has <set> <n>\n       intset add <set> <n>"
    );
    ExitCode::from(2)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();

    match args.len() {
        3 if args[1] == "normalize" => match normalize(&args[2]) {
            Some(text) => {
                println!("{text}");
                ExitCode::SUCCESS
            }
            None => {
                eprintln!("intset: \"{}\" is not a set", args[2]);
                ExitCode::from(1)
            }
        },
        4 if args[1] == "has" || args[1] == "add" => {
            let value: u32 = match args[3].parse() {
                Ok(n) => n,
                Err(_) => {
                    eprintln!("intset: \"{}\" is not a value in 0..4294967295", args[3]);
                    return ExitCode::from(1);
                }
            };
            if args[1] == "has" {
                match contains(&args[2], value) {
                    Some(true) => {
                        println!("yes");
                        ExitCode::SUCCESS
                    }
                    Some(false) => {
                        println!("no");
                        ExitCode::SUCCESS
                    }
                    None => {
                        eprintln!("intset: \"{}\" is not a set", args[2]);
                        ExitCode::from(1)
                    }
                }
            } else {
                match add(&args[2], value) {
                    Some(text) => {
                        println!("{text}");
                        ExitCode::SUCCESS
                    }
                    None => {
                        eprintln!("intset: \"{}\" is not a set", args[2]);
                        ExitCode::from(1)
                    }
                }
            }
        }
        _ => usage(),
    }
}
