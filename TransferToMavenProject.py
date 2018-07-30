#!/usr/bin/python
# -*- coding: UTF-8 -*-
import argparse
import re
import threading
import urllib2
import os
import subprocess

groupIdAndArtifactId = {}
nameVersionDict = {}
javaFiles = []
importList = []

# 爬取maven.aliyun.com的线程
class CrawlThread(threading.Thread):
    def __init__(self, name):
        threading.Thread.__init__(self)
        self.name = name

    def getHtmlUnit(self):
        localVar = threading.local()
        localVar.valid = False
        htmlObj = urllib2.urlopen(
            "http://maven.aliyun.com/nexus/service/local/lucene/search?collapseresults=true&q=" + self.name)
        html = htmlObj.read()
        res = re.search(r'<groupId>(.*)</groupId>\s*<artifactId>(.*)</artifactId>', html)
        if res is None:
            return
        for importStr in importList:  # 第二次过滤：爬取到的groupId必须在java文件的import中出现过，否则，丢弃这个groupId
            if res.group(1) in importStr:
                localVar.valid = True
        if localVar.valid is True:
            groupIdAndArtifactId[self.name] = {"groupId": res.group(1), "artifactId": res.group(2)}


    def run(self):
        localVar = threading.local()
        localVar.success = False
        count = 0
        print "begin " + self.name + " ......"
        while localVar.success is False:  # 增加HTTPError容错机制
            count = count + 1
            if count > 10:                # 第一次过滤：当循环爬取次数超过十次，则结束该线程
                return
            try:
                self.getHtmlUnit()
                localVar.success = True
                print "end " + self.name + " ......"
            except urllib2.HTTPError:
                print "repeat " + self.name + " the " + str(count) + " time"
                continue

# 获取所有java文件
def getJavaFile(javaProjectPath):
    # 遍历filepath下所有文件，包括子目录
    files = os.listdir(javaProjectPath)
    for fi in files:
        fi_d = os.path.join(javaProjectPath, fi)
        if os.path.isdir(fi_d):
            getJavaFile(fi_d)
        else:
            if re.match('.*\.java$', fi) is None:
                continue
            javaFiles.append(os.path.join(javaProjectPath, fi_d))
    return

# 获取所有java文件中的import
def getImports():
    for java in javaFiles:
        with open(java, "r+", 1) as f:
            obj = re.findall(r'import(.*);', f.read())
            importList.extend(obj)
    return




# step1 接收外部传参
def getArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument('--libPath', type=str, help='local lib path')
    parser.add_argument('--xmlPath', type=str, help='settings.xml path')
    parser.add_argument('--localRepository', type=str, help='maven local repository')
    parser.add_argument('--javaProjectPath', type=str, help='source path of java project')
    parser.add_argument('--pomPath', type=str, help='path of pom.xml')

    args = parser.parse_args()
    libPath = args.libPath
    xmlPath = args.xmlPath
    localRepository = args.localRepository
    javaProjectPath = args.javaProjectPath
    pomPath = args.pomPath
    return libPath, xmlPath, localRepository, javaProjectPath, pomPath


# step2 配置maven settings.xml
def configSettingsXml(xmlPath, localRepository):
    replaceStr = r"<localRepository>" + localRepository + "</localRepository>"
    with open(xmlPath, "r+", 1) as f:
        newFile = re.sub(r'<!-- localRepository[\s\S]*?-->', replaceStr, f.read())
    with open(xmlPath, "w", 1) as f:
        f.write(newFile)
    return

# step3 获取本地jar包的name:version字典
def getNameVersionDict(libPath):
    for file in os.listdir(libPath):
        matchObject = re.match(r'(.*)-(\d.*\d)\.*.*\.jar', file)
        if matchObject is None:
            continue
        name = matchObject.group(1)
        version = matchObject.group(2)
        nameVersionDict[name] = version
    print nameVersionDict
    return nameVersionDict


# step4 爬取dependency写法
def getHtml(nameVersionDict):
    threadList = []
    for name in nameVersionDict.keys():
        thread = CrawlThread(name)
        thread.start()
        threadList.append(thread)
    for thread in threadList:  # 多线程爬取，主线程等待所有子线程结束任务
        thread.join()
    return groupIdAndArtifactId


# step5 本地jar包制作成maven包
def installLibsToLocalRepository(libPath):
    for file in os.listdir(libPath):
        localJarPath = libPath + "/" + file
        matchObject = re.match(r'(.*)-(\d.*\d)\.*.*\.jar', file)
        if matchObject is None:
            continue
        name = matchObject.group(1)
        version = matchObject.group(2)
        if name not in groupIdAndArtifactId:  # groupIdAndArtifactId中存了有效的groupId和artifactId
            continue
        print "mvn start " + name
        groupId = groupIdAndArtifactId[name]["groupId"]
        artifactId = groupIdAndArtifactId[name]["artifactId"]
        mvnShell = 'mvn install:install-file -Dfile=' + localJarPath + ' -DgroupId=' + groupId + ' -DartifactId=' + artifactId + ' -Dversion=' + version + ' -Dpackaging=jar'
        print mvnShell
        p = subprocess.call(mvnShell, shell=True)
        print "mvn end " + name
    return


# step6 dependency配置追加到pom.xml
def configPomXml(pomPath):
    allStr = ''
    for name in groupIdAndArtifactId:
        groupId = groupIdAndArtifactId[name]["groupId"]
        artifactId = groupIdAndArtifactId[name]["artifactId"]
        dependency = "<dependency><groupId>" + groupId + "</groupId><artifactId>" + artifactId + "</artifactId><version>" + \
                     nameVersionDict[name] + "</version></dependency>\n"
        allStr = allStr + dependency



    with open(pomPath, "r+", 1) as f:
        newFile = re.sub(r'<dependencies>[\s\S]*</dependencies>', '<dependencies>'+allStr+'</dependencies>', f.read())
    with open(pomPath, "w", 1) as f:
        f.write(newFile)
    return

if __name__ == '__main__':
    libPath, xmlPath, localRepository, javaProjectPath, pomPath = getArgs()
    configSettingsXml(xmlPath, localRepository)
    nameVersionDict = getNameVersionDict(libPath)
    getJavaFile(javaProjectPath)
    getImports()
    getHtml(nameVersionDict)
    installLibsToLocalRepository(libPath)
    configPomXml(pomPath)
