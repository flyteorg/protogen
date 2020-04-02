#

import argparse
import os
import shutil
import subprocess

OUTPUT_DIR = "gen"
OUTPUT_DIR_PREFIX="/pb"
SOURCE_RELATIVE_PARAM = "paths=source_relative,"
DEFAULT_INCLUDES = ["-I=/usr/local/include", "-I=/opt/include"]
PROTODOC_PATH = "/usr/local/bin/protodoc.py"


def add_titles_to_protodoc(base_proto_path, root_dir, output_dir): 
    """
    After the protodoc plugin has been run, we append the contents of title.rst (if it exists) in the protobuf package to index.rst.
    We also automatically create an index that goes from titles.rst in an heirarchical order

    This allows adding common descriptions and documentation per protobuf package.

    General structure for title.rst to work,
    For packages [protos/base_package, protos/base_package/nested_package1, protos/base_package/nested_package2]
    Add title.rst to
    protos/base_package/title.rst
    protos/base_package/nested_package1/title.rst
    protos/base_package/nested_package2/title.rst

    NOTE: Title.rst is completely optional.
    For example refer to
    https://github.com/lyft/flyteidl/tree/master/protos/flyteidl
    """
    for root_dir, dirs, files in os.walk(output_dir):
        index_file_path = os.path.join(root_dir, "index.rst")
        dirname = os.path.basename(root_dir)
        title = "{}\n{}\n".format(dirname, "="*len(dirname))
        package = root_dir[len(output_dir):]
        if package != "" and package[0] == "/":
            package = package[1:]
        original_package = os.path.join(base_proto_path, package)
        precreated_title = os.path.join(original_package, "title.rst")
        if os.path.exists(precreated_title):
            print("Using pre-exising {} -> {}\n".format(precreated_title, index_file_path))
            with open(precreated_title, "r") as forig:
                title = forig.read()

        with open(index_file_path, 'w') as fh:
            fh.write(title)
            fh.write("\n")
            fh.write(".. toctree::\n")
            fh.write("\t:maxdepth: 1\n")
            fh.write("\t:caption: {}\n".format(dirname))
            fh.write("\t:name: {}toc\n".format(dirname))
            fh.write("\n")
            for dname in sorted(dirs):
                fh.write("\t{}/index\n".format(dname))
            for fname in sorted(files):
                if fname != "index.rst":
                    fh.write("\t{}\n".format(os.path.splitext(fname)[0]))


# TODO Refactor this code.

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wraps around the namely/protoc-all container and add protoc-gen-validate"
                                                 "to create proto generated outputs.")

    parser.add_argument('--includes', '-i', action="append", default=[],
                        help="The list of extra includes. By default, `/usr/local/include` and `/opt/include` are passed to protoc")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', '-f', default=None, help="The proto source file to generate.")
    group.add_argument('--directory', '-d', default=None, help="The source directory to search for proto source files.")
    parser.add_argument('--language', '-l', default=None, choices=["go", "python", "cpp", "java", "protodoc"], help="The language to generate for.")
    parser.add_argument('--with_gateway', '-wg', default=False, action="store_true",
                        help="Generate the grpc gateway files(experimental)")
    parser.add_argument('--go_source_relative', default=False, action="store_true",
                        help="Make go import paths 'source_relative - see https://github.com/golang/protobuf#parameters")
    parser.add_argument('--validate_out', '-v', default=False, action="store_true", help="Specifies the input to protoc-gen-validate,"
                                                                  " if not specified the plugin won't be invoked")

    # Validation for constraints that aren't simply verifiable via argparse.

    # Only go outputs can generate grpc-gateway.
    args = parser.parse_args()
    if args.language != "go" and args.with_gateway:
        raise argparse.ArgumentError("Generating grpc-gateway is Go specific")

    # The output directory is under `gen/pb<-LANGUAGE/_python>
    # Python needs underscore for the output directory to be able to read it.
    output_dir = OUTPUT_DIR + OUTPUT_DIR_PREFIX
    if args.language == 'python':
        output_dir += '_python'
    else:
        output_dir += '-' + args.language

    # The output directory needs to exists for protoc to generate outputs.
    os.makedirs(output_dir, exist_ok=True)

    # subprocess.check_output uses an array for passing in arguments. The first arg is the
    # binary name.
    protoc_args = ['protoc']

    # The list of includes will be reused if --with_gateway is specified.
    # The first parameters to protoc are the includes required to resolve the protos.
    includes =list(DEFAULT_INCLUDES)
    # Append the extra includes.
    for extra_include in args.includes:
        includes.append("-I="+extra_include)

    # Only one of file or directory can be specified.
    if args.file:
        # If a single file is specified as input to the script, then the current working directory is added
        # to the includes prior to other includes.
        includes = ["-I=."] + includes
    else:
        # For a directory, the other includes are specified prior to the directory with the protos.
        includes.append("-I="+args.directory)

    protoc_args.extend(includes)

    # The next set of parameters are the language configurations.
    if args.language == 'go':
        go_parameters = "--go_out="
        if args.go_source_relative:
            go_parameters+=SOURCE_RELATIVE_PARAM
        go_parameters+="plugins=grpc:"+output_dir
        protoc_args.append(go_parameters)
    elif args.language == "protodoc":
        protoc_args += ["--plugin=protoc-gen-protodoc="+PROTODOC_PATH,
        "--protodoc_out="+output_dir]
    else:
        protoc_args.append("--"+args.language+"_out="+output_dir)
        if args.language != "java":
            protoc_args.append("--grpc_out=" + output_dir)
            protoc_args.append("--plugin=protoc-gen-grpc="+ shutil.which("grpc_"+args.language+"_plugin"))

    # TODO we are using validate, but @kumare3 thinks it does not work, verify and remove!
    # Generates the validate methods.
    if args.validate_out:
        protoc_args.append("--validate_out=lang="+args.language+":"+output_dir)

    # The list of proto_files will be used again if --with_gateway is specified.
    proto_files = []
    # The final parameters are the protos files to use for generating the output code.
    if args.file:
        proto_files.append(args.file)
    else:
        # For all protos under args.directory, they need to be specified to protoc
        # Remove all tuples that have no files.
        # The tuple output from os.walk is (root, dirs, files) only store the root and the files.
        walk_tuple = [ (item[0], item[2]) for item in os.walk(args.directory) if item[2]]
        # For each tuple, check if a file in files ends with *.proto
        for root_dir, files in walk_tuple:
            for f in files:
                # Add this file to the protoc arguments.
                if f.endswith(".proto"):
                    proto_files.append(root_dir+"/"+f)

    protoc_args.extend(proto_files)

    print(protoc_args)
    try:
        subprocess.check_output(protoc_args, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(str(e.output,"utf-8"))
        exit(1)

    # Python needs __init__.py files in each directory there are outputs for python and up until
    # the root directory that this script is invoked.
    if args.language == 'python':
        # Add `__init__.py` to all subdirectories of the python output.
        for root_dir, _, _ in os.walk(output_dir):
            init_file_path = os.path.join(root_dir, "__init__.py")
            if not os.path.exists(init_file_path):
                with open(init_file_path, 'w') as fh:
                    pass
        # Add '__init__.py' to the source output directory specified by OUTPUT_DIR.
        init_file_path = os.path.join(OUTPUT_DIR, "__init__.py")
        if not os.path.exists(init_file_path):
            with open(init_file_path, 'w') as fh:
                pass

    if args.with_gateway:
        gateway_args =['protoc'] + includes
        gateway_args.append("--grpc-gateway_out=logtostderr=true,allow_delete_body=true:"+output_dir)
        gateway_args.extend(proto_files)
        try:
            subprocess.check_output(gateway_args, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print(str(e.output, "utf-8"))
            exit(1)

        swagger_args = ['protoc'] + includes
        swagger_args.append("--swagger_out=logtostderr=true,allow_delete_body=true:"+output_dir)
        swagger_args.extend(proto_files)
        try:
            subprocess.check_output(swagger_args, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print(str(e.output, "utf-8"))
            exit(1)

    ###################
    # This is an extra step to generate documentation indexes

    # The base proto path is a complete hack, we should re-write protocgenerator as
    # a flyte code generator
    base_proto_path = ""
    if args.includes:
        base_proto_path = args.includes[0]

    if args.language == "protodoc":
        add_titles_to_protodoc(base_proto_path, root_dir, output_dir)
     
