#!/usr/bin/python
'''
Documentation, License etc.

@package github3_test
'''
import os
import sys
import stat
import mimetypes
import shutil
import zipfile
import tarfile
import getpass
import ConfigParser
import argparse
from subprocess import call
import github3


def copy(src, dst):
    if os.path.islink(src):
        linkto = os.readlink(src)
        os.symlink(linkto, dst)
    else:
        shutil.copy(src, dst)


def copyLib(src, dstDir, version=''):
    srcDir = os.path.dirname(src)
    srcName = os.path.basename(src)
    if version == '':
        found = False
        for f in reversed(os.listdir(srcDir)):
            if srcName in f:
                copy(os.path.join(srcDir, f), os.path.join(dstDir, f))
                found = True
        if not found:
            sys.stdout.write("library " + srcName + " not found\n")
            exit(1)
    else:
        srcNameExtended = srcName + '.' + version
        shutil.copy(os.path.join(srcDir, srcNameExtended),
                    os.path.join(dstDir, srcNameExtended))


class QtDeployment:
    def __init__(self):
        self.gh = None
        self.repository = None

    def loginToGitHub(self):
        sys.stdout.write("loging in to GitHub...")
        sys.stdout.flush()
        self.gh = github3.login(self.userName, password=self.userPassword)
        if not self.gh:
            sys.stdout.write("failed\n")
            exit(1)
        sys.stdout.write("done\n")

        self.repository = self.gh.repository(owner=self.repoUser, repository=self.repoName)
        if not self.repository:
            print("Repository not found")
            exit(1)

    def createReleaseTag(self, releaseName):
        return releaseName.lower().replace(' ', '_')

    def updateRelease(self):
        sys.stdout.write("updating release on GitHub...")
        sys.stdout.flush()

        releaseTag = self.createReleaseTag(self.releaseName)
        self.release = None
        for r in self.repository.releases():
            if (r.tag_name == releaseTag):
                self.release = r
                if self.debug:
                    print("release exists")
                break

        if not self.release:
            self.release = self.repository.create_release(tag_name = releaseTag,
                                                          name = self.releaseName,
                                                          body = self.releaseDescription,
                                                          prerelease = self.prerelease,
                                                          draft = self.draft,
                                                          target_commitish = self.gitTag)
        else:
            self.release.edit(tag_name = releaseTag,
                              name = self.releaseName,
                              body = self.releaseDescription,
                              prerelease = self.prerelease,
                              draft = self.draft,
                              target_commitish = self.gitTag)

        sys.stdout.write("done\n")

    def removeRelease(self):
        sys.stdout.write("removing release from GitHub...")
        sys.stdout.flush()

        releaseTag = self.createReleaseTag(self.releaseName)

        self.release = None
        for r in self.repository.iter_releases():
            if (r.tag_name == releaseTag):
                self.release = r
                if self.debug:
                    print("release exists")
                break

        if self.release:
            self.release.delete()
            self.release = None

        sys.stdout.write("done\n")

    def updateAsset(self):
        sys.stdout.write("uploading file to GitHub...")
        sys.stdout.flush()

        if not self.release:
            raise Exception("You must first create a release")

        assetName = os.path.basename(self.zipName)
        assetType = mimetypes.guess_type(self.zipName)
        assetFile = open(self.zipName, 'r')

        asset = None
        if assetFile:
            try:
                asset = self.release.upload_asset(content_type=assetType,
                                            name=assetName,
                                            asset=assetFile)
            except:
                pass
            assetFile.close()

        if not asset:
            sys.stderr.write("uploading file failed\n")
            exit(1)

        sys.stdout.write("done\n")

    def cleanup(self):
        sys.stdout.write("startin cleanup...")
        sys.stdout.flush()

        if os.path.exists(self.deploymentDir):
            shutil.rmtree(self.deploymentDir)

        if os.path.isfile(self.zipName):
            os.remove(self.zipName)

        sys.stdout.write("done\n")

    def deployMac(self):
        self.cleanup()

        sys.stdout.write("creating disk image...")
        sys.stdout.flush()
        macutil = os.path.join(self.qtBinDir, 'macdeployqt')
        targetBundle = os.path.join(self.applicationDir, self.target)
        call([macutil, targetBundle, '-qmldir=' + self.qmlSourceDir, '-dmg'])
        sys.stdout.write("done\n")

        sys.stdout.write("moving disk image...")
        sys.stdout.flush()
        inPath = os.path.join(self.applicationDir, self.dmgName)
        shutil.copyfile(inPath, self.zipName)
        os.remove(inPath)
        sys.stdout.write("done\n")

        sys.stdout.write("cleaning app bundle...")
        sys.stdout.flush()
        shutil.rmtree(targetBundle)
        sys.stdout.write("done\n")

    def deployFiles(self):
        self.cleanup()

        sys.stdout.write("copying files...")
        sys.stdout.flush()
        try:
            os.makedirs(self.outLibDir)
        except WindowsError:    # ignore error on windows
            pass

        if self.qtLibs[0] != '':
            for lib in self.qtLibs:
                # if version os specified copy only libs with this version
                version = ''
                libSplit = lib.split(':')
                lib = libSplit[0]
                if len(libSplit) > 1:
                    version = libSplit[1]

                libName = self.libraryPrefix + lib + self.libraryExtension
                inPath = os.path.join(self.qtLibDir, libName)
                copyLib(inPath, self.outLibDir, version)

        if self.libs[0] != '':
            for lib in self.libs:
                # if version os specified copy only libs with this version
                version = ''
                libSplit = lib.split(':')
                lib = libSplit[0]
                if len(libSplit) > 1:
                    version = libSplit[1]

                libName = lib + self.libraryExtension
                copied = False
                for libDir in self.libDirs:
                    inPath = os.path.join(libDir, libName)
                    found = False
                    if version == '':
                        for f in reversed(os.listdir(libDir)):
                            if libName in f:
                                found = True
                                break
                    else:
                        if os.path.isfile(inPath):
                            found = True
                    if found:
                        copyLib(inPath, self.outLibDir, version)
                        copied = True
                        break

                if not copied:
                    sys.stderr.write('could not find library ' + libName + '\n')
                    exit(1)

        try:
            os.makedirs(self.outPlatformsDir)
        except WindowsError:    # ignore error on windows
            pass

        for plugin in self.platformPlugins:
            pluginName = self.libraryPrefix + plugin + self.libraryExtension
            inPath = os.path.join(self.platformsDir, pluginName)
            outPath = os.path.join(self.outPlatformsDir, pluginName)
            shutil.copyfile(inPath, outPath)

        try:
            os.makedirs(self.outBinDir)
        except WindowsError:    # ignore error on windows
            pass

        inFile = os.path.join(self.applicationDir, self.target)
        targetFile = os.path.join(self.outBinDir, self.target)
        shutil.copyfile(inFile, targetFile)
        if (self.platform == 'linux_x86') or (self.platform == 'linux_x64'):
            st = os.stat(targetFile)
            os.chmod(targetFile, st.st_mode | stat.S_IEXEC)

        if self.qmlPlugins[0] != '':
            for qmlplugin in self.qmlPlugins:
                targetPath = os.path.join(self.outQmlDir, qmlplugin)
                if os.path.exists(targetPath):
                    shutil.rmtree(targetPath)
                shutil.copytree(os.path.join(self.qmlDir, qmlplugin), targetPath)

        if self.qtPlugins[0] != '':
            for qtplugin in self.qtPlugins:
                targetPath = os.path.join(self.outPluginDir, qtplugin)
                if os.path.exists(targetPath):
                    shutil.rmtree(targetPath)
                shutil.copytree(os.path.join(self.pluginDir, qtplugin), targetPath)

        # remove unnecessary files:
        for root, dirs, files in os.walk(self.outQmlDir):
                for f in files:
                    if (f == 'plugins.qmltypes'):
                        os.remove(os.path.join(root, f))

        sys.stdout.write("done\n")

        sys.stdout.write("compressing files...")
        sys.stdout.flush()
        if (self.platform == 'windows_x86') or (self.platform == 'windows_x64'):
            # remove debug libraries
            for root, dirs, files in os.walk(self.deploymentDir):
                    for f in files:
                        if (('d' + self.libraryExtension) in f)  \
                            or (('d.pdb') in f):
                            os.remove(os.path.join(root, f))
            # create zip file
            with zipfile.ZipFile(self.zipName, 'w', zipfile.ZIP_DEFLATED) as myzip:
                for root, dirs, files in os.walk(self.deploymentDir):
                    for f in files:
                        myzip.write(os.path.join(root, f))
                myzip.close()
        elif (self.platform == 'linux_x86') or (self.platform == 'linux_x64'):
            # strip debug information
            for root, dirs, files in os.walk(self.outLibDir):
                    for f in files:
                        if self.libraryExtension in f:
                            call(['strip', os.path.join(root, f)])
            call(['strip', os.path.join(self.outBinDir, self.target)])

            # create run.sh
            runFilePath = os.path.join(self.deploymentDir, self.target)
            runFile = open(runFilePath, 'w')
            if runFile:
                runFile.write('#!/bin/bash\n')
                runFile.write('if [ -z "$BASH_SOURCE" ]; then\n')
                runFile.write('cd "$(dirname "$(readlink -f "$0")")"\n')
                runFile.write('else\n')
                runFile.write('cd "$(dirname "${BASH_SOURCE[0]}" )"\n')
                runFile.write('fi\n')
                runFile.write('export LD_LIBRARY_PATH=`pwd`/lib\n')
                runFile.write('export QML_IMPORT_PATH=`pwd`/qml\n')
                runFile.write('export QML2_IMPORT_PATH=`pwd`/qml\n')
                runFile.write('export QT_QPA_PLATFORM_PLUGIN_PATH=`pwd`/platforms\n')
                runFile.write('export QT_PLUGIN_PATH=`pwd`\n')
                if (self.platform == 'linux_x86'):
                    runFile.write('/lib/ld-linux.so.2 ')
                else:
                    runFile.write('/lib64/ld-linux-x86-64.so.2 ')
                runFile.write('`pwd`/bin/' + self.target + '\n')
                runFile.close()
                st = os.stat(runFilePath)
                os.chmod(runFilePath, st.st_mode | stat.S_IEXEC)
            else:
                sys.stderr.write('error creating ' + runFilePath + '\n')
                exit(1)
            # create tar file
            with tarfile.open(self.zipName, 'w:gz') as mytar:
                for root, dirs, files in os.walk(self.deploymentDir):
                    for f in files:
                        mytar.add(os.path.join(root, f))
                mytar.close()
        sys.stdout.write("done\n")

    def parseConfig(self):
        if self.debug:
            print("parsing config file")

        if self.version:
            defaults = {'version': self.version}
        else:
            defaults = None
        config = ConfigParser.SafeConfigParser(defaults)
        config.read(self.configFile)
        self.name = config.get('DEFAULT', 'name').strip('"')
        try:
            if not self.version:
                self.version = config.get('DEFAULT', 'version').strip('"')
        except:
            self.version = None
        self.platform = config.get('Deployment', 'platform').strip('"')
        self.qtDir = os.path.expanduser(config.get('Deployment', 'qtDir').strip('"'))
        self.applicationDir = os.path.expanduser(config.get('Deployment', 'applicationDir').strip('"'))
        self.pkgName = os.path.expanduser(config.get('Deployment', 'pkgName').strip('"'))
        if self.platform == "mac":
            self.qmlSourceDir = os.path.expanduser(config.get('Deployment', 'qmlSourceDir').strip('"'))
        else:
            self.deploymentDir = os.path.expanduser(config.get('Deployment', 'deploymentDir').strip('"'))
            rawLibDirs = config.get('Deployment', 'libDir').strip('"').split(',')
            self.libDirs = []
            for libDir in rawLibDirs:
                self.libDirs.append(os.path.expanduser(libDir))
            self.qmlPlugins = config.get('Deployment', 'qmlPlugins').strip('"').split(',')
            self.qtPlugins = config.get('Deployment', 'qtPlugins').strip('"').split(',')
            self.platformPlugins = config.get('Deployment','platformPlugins').strip('"').split(',')
            self.qtLibs = config.get('Deployment', 'qtLibs').strip('"').split(',')
            self.libs = config.get('Deployment', 'libs').strip('"').split(',')
        try:
            if not self.userName:
                self.userName = config.get('GitHub', 'user').strip('"')
        except:
            self.userName = None
        try:
            if not self.userPassword:
                self.userPassword = config.get('GitHub', 'password').strip('"')
        except:
            self.userPassword = None
        [self.repoUser, self.repoName] = config.get('GitHub', 'repo').strip('"').split('/')
        self.releaseName = config.get('Release', 'name').strip('"')
        self.descriptionFile = config.get('Release', 'description').strip('"')

    def parseArguments(self):
        parser = argparse.ArgumentParser(description='Component for easy deployment of Qt applications')
        parser.add_argument('-v', '--version', help='Version of the application', required=None)
        parser.add_argument('-u', '--user', help='GitHub user name', default=None)
        parser.add_argument('-p', '--password', help='GitHub password', default=None)
        parser.add_argument('-dr', '--draft', help='Publish on GitHub as draft', action='store_true')
        parser.add_argument('-pr', '--prerelease', help='Publish on GitHub as pre-release', action='store_true')
        parser.add_argument('-t', '--tag', help='Git tag of the release', default=None)
        parser.add_argument('--deploy', help='Deploy the application to the output directory', action='store_true')
        parser.add_argument('--publish', help='Upload the application to GitHub', action='store_true')
        parser.add_argument('--unpublish', help='Remove the release from GitHub', action='store_true')
        parser.add_argument('--clean', help='Cleanup the created files afterwards', action='store_true')
        parser.add_argument('-d', '--debug', help='Whether debug output should be enabled or not', action='store_true')
        parser.add_argument('config', help='Config file', nargs='?', default=None)
        args = parser.parse_args()

        self.version = args.version
        self.userName = args.user
        self.userPassword = args.password
        self.draft = args.draft
        self.prerelease = args.prerelease
        self.debug = args.debug
        self.deploy = args.deploy
        self.publish = args.publish
        self.unpublish = args.unpublish
        self.clean = args.clean
        self.configFile = args.config
        self.gitTag = args.tag

        if self.debug:
            print("parsed arguments")

        if not self.configFile:
            print("no config file specified")
            exit(1)

    def createVars(self):
        if self.debug:
            print("creating variables")

        if (self.platform == 'windows_x86') or (self.platform == 'windows_x64'):
            self.targetExtension = '.exe'
            self.libraryExtension = '.dll'
            self.libraryPrefix = ''
            self.zipName = self.pkgName + '.zip'
            self.qtLibDir = os.path.join(self.qtDir, 'bin')
            self.outLibDir = self.deploymentDir
            self.outBinDir = self.deploymentDir
        elif (self.platform == 'linux_x86') or (self.platform == 'linux_x64'):
            self.targetExtension = ''
            self.libraryExtension = '.so'
            self.libraryPrefix = 'lib'
            self.zipName = self.pkgName + '.tar.gz'
            self.qtLibDir = os.path.join(self.qtDir, 'lib')
            self.outLibDir = os.path.join(self.deploymentDir, 'lib')
            self.outBinDir = os.path.join(self.deploymentDir, 'bin')
        elif (self.platform == 'mac'):
            self.targetExtension = '.app'
            self.qtBinDir = os.path.join(self.qtDir, 'bin')
            self.zipName = self.pkgName + '.dmg'
            self.dmgName = self.name + '.dmg'
            self.deploymentDir = ''
        else:
            self.targetExtension = ''
            self.libraryExtension = ''
            self.qtDir = os.path.join(self.qtDir, 'lib')

        self.target = self.name.lower() + self.targetExtension
        self.qmlDir = os.path.join(self.qtDir, 'qml')
        self.pluginDir = os.path.join(self.qtDir, 'plugins')
        self.platformsDir = os.path.join(self.qtDir, 'plugins/platforms')
        self.outPluginDir = self.deploymentDir
        self.outPlatformsDir = os.path.join(self.deploymentDir, 'platforms')
        self.outQmlDir = os.path.join(self.deploymentDir, 'qml')

        self.releaseDescription = ''
        if os.path.exists(self.descriptionFile):
            f = open(self.descriptionFile)
            if f:
                self.releaseDescription = f.read()

    def checkCredentials(self):
        if not self.userName:
            self.userName = raw_input('GitHub username: ')
        if not self.userPassword:
            self.userPassword = getpass.getpass('GitHub password: ')

    def run(self):
        self.parseArguments()
        self.parseConfig()
        self.createVars()
        if self.deploy:
            if self.platform == 'mac':
                self.deployMac()
            else:
                self.deployFiles()
        if self.publish:
            self.checkCredentials()
            self.loginToGitHub()
            self.updateRelease()
            self.updateAsset()
        if self.unpublish:
            self.checkCredentials()
            self.loginToGitHub()
            self.removeRelease()
        if self.clean:
            self.cleanup()

deployment = QtDeployment()
deployment.run()
