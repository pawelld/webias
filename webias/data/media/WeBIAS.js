/*
 Copyright 2013 Pawel Daniluk, Bartek Wilczynski
 
 This file is part of WeBIAS.
 
 WeBIAS is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as 
 published by the Free Software Foundation, either version 3 of 
 the License, or (at your option) any later version.
 
 WeBIAS is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.
 
 You should have received a copy of the GNU Affero General Public 
 License along with WeBIAS. If not, see 
 <http://www.gnu.org/licenses/>.
*/

function addElement(event) {
	button=$(event.target);
	group=button.closest("div.vargroup");
	template=group.children("div.template");

	c=template.clone(true);

	c.removeClass("template")

	group.append(c);

	n=group.data("count");
	n++;
	group.data("count",n);

	updateAdd(group);

	c.slideDown(100,function(){
		fixRemove(c);
	});
};

function storeName(t) {
	t.data("name", t.attr("name"));
}

function getName(t) {
	if(t.is('[name], .vargroup')) {
		varel=t.closest(".varelement");

		if(varel.length) {
			return getName(varel)+'/'+t.data("name");
		}

		return t.data("name");
	}

	if(t.is('.varelement')) {
		if(t.is('.template')){
			return '///';
		}

		group=t.closest(".vargroup");

		return getName(group)+':'+(t.prevAll('.varelement').length+1);
	}
}

function fixRemove(c) {
	b=c.find("button.remove").first();

	el=c.children("div.element").first().children("div.group").first();

	pos=$(document);
	offset='-8 0'

	if (el.find("div.group,div.section,div.vargroup").length>0) {
		first_child=el.children().first();
		if(first_child.is("div.section")){
			pos=first_child;
		} else if(first_child.is("div.element") && ! first_child.find("div.group").length>0) {
			pos=first_child;
			offset='0 0'
		} else {
			el.prepend('<div class="section section-light">&nbsp;</div>');
			pos=el.children().first();
		}
	} else {
		pos=el;
	}

	b.fadeIn(100);
	b.position({of: pos, my:'right middle', at:'right middle', offset:offset});
}

function updateAdd(group) {
	n=group.data("count");
	b=group.children(".section").first().children("button.add")

	if(n>=group.data("max")) {
		b.attr("disabled","disabled")
	} else {
		b.removeAttr("disabled")
	}
}

function removeElement(event) {
	varel=$(event.target).closest(".varelement");

	group=varel.closest("div.vargroup");

	n=group.data("count");
	n--;
	group.data("count",n);


	updateAdd(group);
	
	varel.slideUp(100, function(){
		varel.detach();
	});
};
