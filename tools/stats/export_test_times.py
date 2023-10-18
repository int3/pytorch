import subprocess


def get_sha_of_generated_stats_branch():
    command = "git ls-remote https://github.com/pytorch/test-infra generated-stats"
    return subprocess.check_output(command.split(" ")).decode("utf-8").split()[0]


def main() -> None:
    with open("test-infra_generated-stats_branch_sha.txt", "w") as f:
        f.write(get_sha_of_generated_stats_branch())


if __name__ == "__main__":
    main()
