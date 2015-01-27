all:
	mkdir -p release
	zip -rv release/service.wemo.lightswitch.zip service.wemo.lightswitch -x *.git* -x *.DS_Store -x *.pyc
	
clean:
	rm -fr release/
